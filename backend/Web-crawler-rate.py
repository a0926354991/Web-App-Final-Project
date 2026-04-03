"""
NTU Rating (rating.myntu.me) 列表 → 詳情頁爬蟲。

搜尋頁須先按「查詢」並捲動；課程列以 <a><h6>課名</h6></a> 呈現，自動化環境下
href 可能尚未帶路徑，故改以 h6 辨識卡片。詳情頁 URL 多為 /course-overview/<id>，
採同一分頁點擊後 driver.back()。
"""

from __future__ import annotations

import csv
import json
import random
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# --- 設定 ---
DEBUG = True
LIST_PAGE_TIMEOUT = 90
DETAIL_PAGE_TIMEOUT = 40
DETAIL_MAX_RETRIES = 3
AFTER_DETAIL_LOAD_SLEEP = 1.5
LIST_AFTER_PAGE_TURN_SLEEP = 3.0
# 詳情頁評價區：無限捲動載入更多卡片時，最多捲動輪數（避免死迴圈）
REVIEW_SCROLL_MAX_ROUNDS = 40
REVIEW_SCROLL_STABLE_TO_STOP = 2

# 試跑：設為正整數時只抓前 N 筆即停止（例如 10）；改為 None 表示不限制、跑完全部頁面
MAX_COURSES_TOTAL: int | None = None

_BACKEND = Path(__file__).resolve().parent
OUTPUT_CSV = _BACKEND / "data" / "ntu_rate_data.csv"

# 隨機 User-Agent（降低單一特徵）
_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
)

# 課程卡片：<a> 內含 h6 標題；排除分頁列 nav
COURSE_CARD_XPATH = "//a[.//h6][not(ancestor::nav[@aria-label='pagination navigation'])]"


def _is_course_detail_url(url: str) -> bool:
    """站方詳情頁為 /course-overview/<id>，不一定是 /course/。"""
    u = url.lower()
    return "/course-overview/" in u or "/course/" in u


def _ensure_data_dir() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)


def _write_rate_csv(all_data: list[dict]) -> None:
    """
    寫入 CSV：評價內容若為 List，改存 JSON 字串，避免 Excel／pandas 讀取時因引號、逗號跑格。
    缺失值（None／NaN）統一為空白，不與真實 0.0 混淆。
    """
    rows: list[dict] = []
    for item in all_data:
        row = dict(item)
        vc = row.get("評價內容")
        if isinstance(vc, list):
            row["評價內容"] = json.dumps(vc, ensure_ascii=False)
        rows.append(row)
    pd.DataFrame(rows).to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
        na_rep="",
        quoting=csv.QUOTE_MINIMAL,
    )


def _save_detail_error_screenshot(driver: webdriver.Chrome, reason: str) -> Path:
    """
    詳情頁 Timeout / 診斷用：固定存到 backend/data，檔名含時間與原因。
    """
    _ensure_data_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:80]
    path = _BACKEND / "data" / f"error_detail_{safe}_{ts}.png"
    try:
        driver.save_screenshot(str(path))
        print(f"[診斷截圖] 已儲存: {path} （URL: {driver.current_url}）")
    except Exception as e:
        print(f"[診斷截圖] 儲存失敗: {e}")
        path = _BACKEND / "data" / "error.png"
        try:
            driver.save_screenshot(str(path))
            print(f"[診斷截圖] 已改存 fallback: {path}")
        except Exception as e2:
            print(f"[診斷截圖] fallback 仍失敗: {e2}")
    return path


def _switch_to_latest_window_if_needed(driver: webdriver.Chrome) -> None:
    """若點課程後開了新分頁，切到最後一個視窗。"""
    handles = driver.window_handles
    if len(handles) > 1:
        driver.switch_to.window(handles[-1])


def _leave_detail_return_to_list(driver: webdriver.Chrome) -> None:
    """離開詳情：多視窗則關閉目前分頁並切回列表視窗；單一分頁則 history.back。"""
    if len(driver.window_handles) > 1:
        driver.close()
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
        return
    if _is_course_detail_url(driver.current_url):
        driver.back()


def _maybe_human_scroll_detail(driver: webdriver.Chrome) -> None:
    """模擬真人小幅、隨機捲動，促進 SPA 掛載。"""
    try:
        for _ in range(random.randint(2, 4)):
            dy = random.randint(120, 420)
            driver.execute_script("window.scrollBy(0, arguments[0]);", dy)
            time.sleep(random.uniform(0.15, 0.45))
        driver.execute_script(
            "window.scrollTo(0, Math.min(document.body.scrollHeight, 800));"
        )
        time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass


def _body_has_meaningful_content(driver: webdriver.Chrome) -> bool:
    """page_source 若幾乎只有 head / body 空白，可能是被擋或尚未 hydrate。"""
    try:
        src = driver.page_source or ""
        if "</body>" in src.lower():
            body_start = src.lower().find("<body")
            body_end = src.lower().find("</body>")
            if body_start != -1 and body_end != -1:
                body_snip = src[body_start : body_end + 7]
                if len(body_snip.strip()) < 80:
                    return False
        inner = driver.execute_script(
            "return document.body && document.body.innerText ? document.body.innerText.length : 0;"
        )
        return bool(inner and int(inner) > 30)
    except Exception:
        return True


def _debug_dump(driver: webdriver.Chrome, tag: str) -> None:
    if not DEBUG:
        return
    print(f"\n[DEBUG {tag}] URL: {driver.current_url}")
    try:
        src = driver.page_source or ""
        print(f"[DEBUG {tag}] page_source[:800]:\n{src[:800]}\n--- end snippet ---\n")
    except Exception as e:
        print(f"[DEBUG {tag}] page_source 失敗: {e}")
    try:
        shot = _BACKEND / "data" / f"debug_{tag}.png"
        driver.save_screenshot(str(shot))
        print(f"[DEBUG {tag}] 截圖已存: {shot}")
    except Exception as e:
        print(f"[DEBUG {tag}] 截圖失敗: {e}")


def _debug_list_diag(driver: webdriver.Chrome) -> None:
    if not DEBUG:
        return
    try:
        h6_links = len(driver.find_elements(By.XPATH, COURSE_CARD_XPATH))
        href_links = int(
            driver.execute_script(
                'return document.querySelectorAll(\'a[href*="/course/"]\').length;'
            )
            or 0
        )
        print(f"[DEBUG] 課程卡片(a+h6)數={h6_links}, a[href*='/course/']數={href_links}")
    except Exception as e:
        print(f"[DEBUG] 診斷失敗: {e}")


def _dismiss_overlays(driver: webdriver.Chrome) -> None:
    """關閉可能擋住「查詢」或列表的遮罩（與自動化互動有關）。"""
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        body.send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.2)


def _dismiss_mui_backdrops(driver: webdriver.Chrome) -> None:
    """
    MUI 的 MuiBackdrop-root 會擋住「查詢」造成 ElementClickIntercepted。
    以 JS 隱藏遮罩並 Esc（僅供自動化；一般使用者應等動畫結束）。
    """
    try:
        driver.execute_script(
            """
            document.querySelectorAll('.MuiBackdrop-root').forEach(function (el) {
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
                el.style.opacity = '0';
            });
            """
        )
    except Exception:
        pass
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass
    time.sleep(0.12)


def _click_search_button(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """查詢鈕常被 MUI Backdrop 擋住；每次重試重新定位，避免 stale。"""
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            _dismiss_mui_backdrops(driver)
            btn = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[contains(normalize-space(), '查詢')]")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                btn,
            )
            time.sleep(0.2)
            _dismiss_mui_backdrops(driver)
            driver.execute_script("arguments[0].click();", btn)
            print("已點擊「查詢」，等待列表載入…")
            return
        except StaleElementReferenceException as e:
            last_err = e
            time.sleep(0.35)
        except Exception as e:
            last_err = e
            time.sleep(0.35)
    if last_err:
        raise last_err
    raise RuntimeError("_click_search_button: 未預期結束")


def _scroll_to_reveal_course_list(driver: webdriver.Chrome) -> None:
    """
    捲動以露出列表懶載入。若 execute_script 逾時（頁面卡頓／長時運行），改送 END 鍵後備。
    """

    def _js_scroll(code: str) -> bool:
        try:
            driver.execute_script(code)
            return True
        except TimeoutException:
            return False
        except Exception:
            return False

    if not _js_scroll("window.scrollTo(0, 0);"):
        pass
    time.sleep(0.12)
    for _ in range(6):
        if not _js_scroll(
            "window.scrollBy(0, Math.min(900, window.innerHeight * 0.85));"
        ):
            break
        time.sleep(0.32)
    if not _js_scroll(
        "window.scrollTo(0, Math.max(0, document.body.scrollHeight || 0));"
    ):
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        except Exception:
            pass
    time.sleep(0.45)


def _wait_list_ready(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    """以「含 h6 的課程 <a>」為準，不依賴 href 已寫入。"""
    try:
        wait.until(lambda d: "rating.myntu.me" in d.current_url)
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        wait.until(
            lambda d: len(d.find_elements(By.XPATH, COURSE_CARD_XPATH)) > 0
        )
        return True
    except TimeoutException:
        _debug_dump(driver, "list_wait_timeout")
        _debug_list_diag(driver)
        return False


def _detail_ready_predicate(driver: webdriver.Chrome) -> bool:
    """詳情頁主標題多為 MUI Typography 的 h6（非 h1），一併偵測側欄標籤。"""
    if driver.find_elements(By.CSS_SELECTOR, "main h6, main h1, article h6, article h1"):
        return True
    if driver.find_elements(By.TAG_NAME, "h6"):
        return True
    if driver.find_elements(
        By.CSS_SELECTOR, ".course-title, [class*='course-title'], [class*='CourseTitle']"
    ):
        return True
    if driver.find_elements(By.XPATH, "//*[contains(text(), '授課教師')]"):
        return True
    if driver.find_elements(By.XPATH, "//*[contains(text(), '開課系所')]"):
        return True
    if driver.find_elements(By.CSS_SELECTOR, "main h1, main h2, article h1"):
        return True
    return False


def _wait_detail_ready(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """
    放寬等待：h1 / .course-title / 含「授課教師」節點等皆可。
    若內文過短則先模擬捲動再重試等待。
    Loading 時 MuiBackdrop 會擋內容，先等其消失（或逾時後強制關閉）。
    """
    try:
        WebDriverWait(driver, 20).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".MuiBackdrop-root"))
        )
    except TimeoutException:
        _dismiss_mui_backdrops(driver)

    if not _body_has_meaningful_content(driver):
        _maybe_human_scroll_detail(driver)
        _dismiss_mui_backdrops(driver)

    dw = WebDriverWait(driver, DETAIL_PAGE_TIMEOUT)
    try:
        dw.until(lambda d: _detail_ready_predicate(d))
    except TimeoutException:
        _maybe_human_scroll_detail(driver)
        _dismiss_mui_backdrops(driver)
        try:
            WebDriverWait(driver, 12).until(lambda d: _detail_ready_predicate(d))
        except TimeoutException:
            _save_detail_error_screenshot(driver, "wait_detail_ready_timeout")
            _debug_dump(driver, "detail_ready_timeout")
            raise

    time.sleep(AFTER_DETAIL_LOAD_SLEEP)

    def _detail_sidebar_or_title_loaded(d: webdriver.Chrome) -> bool:
        return bool(
            d.find_elements(By.XPATH, "//*[contains(text(), '授課教師')]")
            or d.find_elements(By.XPATH, "//*[contains(text(), '開課系所')]")
            or d.find_elements(By.XPATH, "//main//h6")
            or d.find_elements(By.XPATH, "//article//h6")
        )

    try:
        WebDriverWait(driver, 12).until(_detail_sidebar_or_title_loaded)
    except TimeoutException:
        try:
            WebDriverWait(driver, 6).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(normalize-space(.), '品質')]")
                )
            )
        except TimeoutException:
            _save_detail_error_screenshot(driver, "detail_sidebar_timeout")
            _debug_dump(driver, "detail_partial_timeout")

    # 平均分數區塊（四維度）常晚於標題載入
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//*[contains(normalize-space(.), '平均分數') or "
                    "(contains(normalize-space(.), '品質') and contains(normalize-space(.), '涼度'))]",
                )
            )
        )
    except TimeoutException:
        pass


def _wait_back_on_search_list(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    wait.until(lambda d: "/search/" in d.current_url)
    wait.until(
        lambda d: len(d.find_elements(By.XPATH, COURSE_CARD_XPATH)) > 0
    )


def _find_next_page_button(driver: webdriver.Chrome):
    try:
        return driver.find_element(By.CSS_SELECTOR, "button[aria-label='Go to next page']")
    except Exception:
        pass
    try:
        nav = driver.find_element(By.CSS_SELECTOR, "nav[aria-label='pagination navigation']")
        buttons = nav.find_elements(By.TAG_NAME, "button")
        if buttons:
            return buttons[-1]
    except Exception:
        pass
    return None


def _click_next_page_button(driver: webdriver.Chrome) -> None:
    """
    下一頁常被底部 sticky／footer／MuiBackdrop 擋住而 ElementClickIntercepted。
    先捲到頁底再上移一點、關遮罩，再點；失敗則改 JS click（React 仍會收到 click）。
    """
    last_err: Exception | None = None
    for attempt in range(6):
        try:
            _dismiss_mui_backdrops(driver)
            try:
                driver.execute_script(
                    "window.scrollTo(0, Math.max(0, document.body.scrollHeight));"
                )
                time.sleep(0.15)
                # 略往上捲，避免分頁鈕落在底欄／cookie 條正下方
                driver.execute_script("window.scrollBy(0, -180);")
            except Exception:
                pass
            time.sleep(0.2 + min(attempt, 3) * 0.1)

            btn = _find_next_page_button(driver)
            if btn is None:
                raise TimeoutException("找不到下一頁按鈕")
            if not btn.is_enabled():
                raise TimeoutException("已到最後一頁（下一頁已停用）")

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});",
                btn,
            )
            time.sleep(0.4)
            btn = _find_next_page_button(driver)
            if btn is None or not btn.is_enabled():
                raise TimeoutException("已到最後一頁（下一頁已停用）")

            try:
                btn.click()
                return
            except Exception as e:
                last_err = e
                try:
                    btn = _find_next_page_button(driver)
                    if btn is None:
                        raise
                    driver.execute_script("arguments[0].click();", btn)
                    return
                except Exception as e2:
                    last_err = e2
                    time.sleep(0.45)
                    continue
        except StaleElementReferenceException:
            last_err = None
            time.sleep(0.35)
            continue
        except TimeoutException:
            raise
        except Exception as e:
            last_err = e
            time.sleep(0.4)

    if last_err:
        raise last_err
    raise RuntimeError("_click_next_page_button: 重試耗盡仍無法點擊下一頁")


def _ensure_on_search_list(
    driver: webdriver.Chrome, base_url: str, wait: WebDriverWait
) -> None:
    """翻頁前須在 /search/；若卡在 course-overview 等頁面則 back 或重開列表。"""
    if "/search/" in driver.current_url:
        return
    for _ in range(5):
        if _is_course_detail_url(driver.current_url):
            driver.back()
            time.sleep(0.8)
        if "/search/" in driver.current_url:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return
    print("無法返回搜尋頁，重新載入列表 URL（將從第 1 頁狀態繼續，若需固定頁碼請改用手動 URL）。")
    driver.get(base_url)
    wait.until(lambda d: "/search/" in d.current_url)


def _normalize_dash_value(raw: str | None) -> str | None:
    """
    將 '--'、'––'（無評分）、全形／半形破折等視為無資料（null）。
    """
    if raw is None:
        return None
    s = (raw or "").strip().replace("\u200b", "").replace("\ufeff", "")
    compact = s.replace(" ", "").replace("　", "")
    if not compact:
        return None
    if compact in ("", "--", "–", "—", "－", "~~", "無", "N/A", "n/a", "––"):
        return None
    if len(compact) <= 3 and set(compact) <= set("-–—－~～."):
        return None
    return s


def _span_value_after_label(driver: webdriver.Chrome, label: str) -> str | None:
    """側邊欄：//span[欄位名]/following-sibling::span（MUI 常見）。"""
    xpaths = (
        f"//span[normalize-space()='{label}']/following-sibling::span[1]",
        f"//span[text()='{label}']/following-sibling::span[1]",
        f"//*[normalize-space()='{label}']/following-sibling::span[1]",
    )
    for xp in xpaths:
        try:
            el = driver.find_element(By.XPATH, xp)
            t = (el.text or "").strip()
            if t:
                return t
        except Exception:
            continue
    return None


def _extract_h6_title_and_professor(driver: webdriver.Chrome) -> tuple[str, str | None]:
    """
    詳情頁主標題為單一 h6：「課名/教授」；另有一顆 h6 可能是「還沒有評價」須排除。
    """
    for h in driver.find_elements(By.XPATH, "//h6"):
        t = (h.text or "").strip()
        if not t or "還沒有評價" in t or "目前還沒有評價" in t:
            continue
        if "/" in t:
            left, right = t.split("/", 1)
            return left.strip(), right.strip()
        return t, None
    try:
        h = driver.find_element(By.TAG_NAME, "h6")
        t = (h.text or "").strip()
        if "/" in t:
            a, b = t.split("/", 1)
            return a.strip(), b.strip()
        return t or "N/A", None
    except Exception:
        return "N/A", None


def _table_serial_code_from_td(driver: webdriver.Chrome) -> tuple[str | None, str | None]:
    """站方表格：tbody/tr 第 2、3 欄為流水號、課號（略過表頭列）。"""
    for tr in driver.find_elements(By.XPATH, "//table//tbody//tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) < 3:
            continue
        c2 = (tds[1].text or "").strip()
        c3 = (tds[2].text or "").strip()
        if c2 == "流水號" or c3 == "課號" or "流水號" in (tds[0].text or ""):
            continue
        return _normalize_dash_value(tds[1].text), _normalize_dash_value(tds[2].text)
    return None, None


def _expand_review_show_more_buttons(driver: webdriver.Chrome) -> None:
    """展開長評價（PTT 轉載等），避免只抓到摺疊前的片段。"""
    try:
        driver.execute_script(
            """
            document.querySelectorAll('button').forEach(function(btn) {
                var t = (btn.innerText || '').trim();
                if (t === '顯示更多') { btn.click(); }
            });
            """
        )
    except Exception:
        pass
    time.sleep(0.35)


def _semester_from_card_chips(card) -> str:
    chips = card.find_elements(
        By.XPATH, ".//span[contains(@class, 'MuiChip-label')]"
    )
    for c in chips:
        t = (c.text or "").strip()
        if not t:
            continue
        if "-" in t and any(ch.isdigit() for ch in t):
            return t
    if chips:
        return (chips[0].text or "").strip()
    return ""


def _score_str_to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = (raw or "").strip().replace("，", ".")
    norm = _normalize_dash_value(s)
    if norm is None:
        return None
    try:
        return float(norm)
    except ValueError:
        return None


def _card_dimension_score(card, dim: str) -> str | None:
    """單張評價卡片內的四維分數（與詳情頁相同 parent::span 邏輯，範圍限於 card）。"""
    for xp in (
        f".//span[contains(text(), '{dim}')]/parent::span[contains(@class, 'MuiTypography-body1')]",
        f".//span[contains(text(), '{dim}')]/parent::span",
    ):
        try:
            el = card.find_element(By.XPATH, xp)
            full = (el.text or "").strip()
            if not full:
                continue
            tail = full.replace(dim, "", 1).strip()
            while dim in tail:
                tail = tail.replace(dim, "", 1).strip()
            if not tail:
                return None
            if tail in ("--", "–", "—", "––", "~~"):
                return None
            if any(ch.isdigit() for ch in tail) and len(tail) <= 12:
                return tail
        except Exception:
            continue
    return None


def _count_review_cards(driver: webdriver.Chrome) -> int:
    """用 MuiCard 總數判斷是否還在載入（含非評價卡，僅作捲動穩定度參考）。"""
    n = len(
        driver.find_elements(By.XPATH, "//main//div[contains(@class, 'MuiCard-root')]")
    )
    if n:
        return n
    return len(driver.find_elements(By.XPATH, "//div[contains(@class, 'MuiCard-root')]"))


def _scroll_reviews_load_more(driver: webdriver.Chrome) -> None:
    """向下捲動直到評價卡片數穩定，以載入 infinite scroll 追加的評價。"""
    last: int | None = None
    stable = 0
    for _ in range(REVIEW_SCROLL_MAX_ROUNDS):
        n = _count_review_cards(driver)
        if last is not None and n == last:
            stable += 1
            if stable >= REVIEW_SCROLL_STABLE_TO_STOP:
                break
        else:
            stable = 0
        last = n
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            break
        time.sleep(0.55)
        _expand_review_show_more_buttons(driver)


def _scrape_reviews_block(driver: webdriver.Chrome) -> tuple[list[dict], list[str]]:
    """
    回傳 (結構化評價列, 可讀摘要列)。
    結構化鍵：User_ID, Semester, Rating_Quality, Rating_Sweet, Rating_Easy, Rating_Rich, Comment
    （對應品質／甜度／涼度／紮實；無分數為 null）
    """
    if driver.find_elements(
        By.XPATH,
        "//h6[contains(.,'還沒有評價') or contains(.,'目前還沒有評價')]",
    ):
        return [], ["無評價"]

    try:
        driver.execute_script(
            "window.scrollTo(0, Math.max(0, document.body.scrollHeight * 0.45));"
        )
        time.sleep(0.35)
    except Exception:
        pass

    _scroll_reviews_load_more(driver)
    for _ in range(2):
        _expand_review_show_more_buttons(driver)

    structured: list[dict] = []
    readable: list[str] = []
    card_xpaths = (
        "//main//div[contains(@class, 'MuiCard-root')]",
        "//div[contains(@class, 'MuiCard-root')]",
    )
    cards: list = []
    for xp in card_xpaths:
        cards = driver.find_elements(By.XPATH, xp)
        if cards:
            break

    for card in cards:
        try:
            if not card.find_elements(
                By.XPATH, ".//span[contains(@class, 'MuiCardHeader-title')]"
            ):
                continue
            if not card.find_elements(
                By.XPATH, ".//div[contains(@class, 'MuiCardContent-root')]"
            ):
                continue
            user = card.find_element(
                By.XPATH, ".//span[contains(@class, 'MuiCardHeader-title')]"
            ).text.strip()
            if not user:
                continue
            semester = _semester_from_card_chips(card)
            content_els = card.find_elements(
                By.XPATH,
                ".//div[contains(@class, 'MuiCardContent-root')]"
                "//span[contains(@class, 'MuiTypography-body2')]",
            )
            parts: list[str] = []
            for el in content_els:
                tx = (el.text or "").strip()
                if not tx or tx == "顯示更多":
                    continue
                parts.append(tx)
            full_content = "\n".join(parts).strip()
            if not full_content:
                continue
            rq = _score_str_to_float(_card_dimension_score(card, "品質"))
            rs = _score_str_to_float(_card_dimension_score(card, "甜度"))
            re = _score_str_to_float(_card_dimension_score(card, "涼度"))
            rr = _score_str_to_float(_card_dimension_score(card, "紮實"))
            row = {
                "User_ID": user,
                "Semester": semester or None,
                "Rating_Quality": rq,
                "Rating_Sweet": rs,
                "Rating_Easy": re,
                "Rating_Rich": rr,
                "Comment": full_content,
            }
            structured.append(row)
            readable.append(f"[{user} | {semester}]: {full_content}")
        except Exception:
            continue

    if structured:
        return structured, readable

    prose: list[str] = []
    for el in driver.find_elements(
        By.XPATH,
        "//div[contains(@class,'review-content') or contains(@class,'prose')]",
    ):
        t = (el.text or "").strip().replace("\n", " ")
        if t:
            prose.append(t)
    if prose:
        fallback = "\n\n".join(prose)
        return (
            [
                {
                    "User_ID": None,
                    "Semester": None,
                    "Rating_Quality": None,
                    "Rating_Sweet": None,
                    "Rating_Easy": None,
                    "Rating_Rich": None,
                    "Comment": fallback,
                }
            ],
            prose,
        )
    return [], ["（未解析到評價段落）"]


def _text_by_label_pair(driver: webdriver.Chrome, label: str) -> str | None:
    """
    成對出現的標籤／值：MUI 常見為兄弟節點 div+p+span。
    若下一格是「另一個欄位標籤」（如 開課系所）則略過，避免誤抓。
    """
    other_labels = {
        "授課教師",
        "開課系所",
        "學分數",
        "最後開課學期",
        "流水號",
        "課號",
    } - {label}
    xpaths = [
        f"//*[normalize-space()='{label}']/following-sibling::*[1]",
        f"//div[normalize-space()='{label}']/following-sibling::div[1]",
        f"//*[self::div or self::p or self::span][normalize-space()='{label}']/following-sibling::*[1]",
        f"//*[normalize-space()='{label}']/following-sibling::*[2]",
        f"//*[normalize-space()='{label}']/parent::*/following-sibling::*[1]//*[self::div or self::p or self::span][1]",
    ]
    for xp in xpaths:
        try:
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                t = (el.text or "").strip()
                if not t or t == label:
                    continue
                if t in other_labels:
                    continue
                return t
        except Exception:
            continue
    return None


def _is_table_header_token(s: str) -> bool:
    """同列若為表頭「流水號|課號」，下一格可能是欄名而非數值。"""
    t = (s or "").strip()
    return t in ("流水號", "課號", "學年期", "課程識別碼")


def _parse_serial_and_course_id(driver: webdriver.Chrome) -> tuple[str | None, str | None]:
    """
    站方表格常見兩種：
    (A) 表頭列：流水號 | 課號，下一列才是數字（不可取「流水號」的 sibling「課號」當流水號）。
    (B) 每列一組：左欄標籤、右欄數值。
    """
    serial: str | None = None
    code: str | None = None

    tables = driver.find_elements(By.CSS_SELECTOR, "main table, article table, table")
    for table in tables:
        rows = table.find_elements(By.CSS_SELECTOR, "tr")
        for i, tr in enumerate(rows):
            tds = tr.find_elements(By.CSS_SELECTOR, "td, th")
            if len(tds) < 2:
                continue
            a = (tds[0].text or "").strip()
            b = (tds[1].text or "").strip()

            # (A) 表頭列 + 下一列數值
            if a == "流水號" and b == "課號" and i + 1 < len(rows):
                vals = rows[i + 1].find_elements(By.CSS_SELECTOR, "td, th")
                if len(vals) >= 2:
                    s_raw = (vals[0].text or "").strip()
                    c_raw = (vals[1].text or "").strip()
                    if s_raw and not _is_table_header_token(s_raw):
                        serial = _normalize_dash_value(s_raw) or serial
                    if c_raw and not _is_table_header_token(c_raw):
                        code = _normalize_dash_value(c_raw) or code
                continue

            # (B) 左欄為標籤、右欄為值（排除右欄仍是欄名）
            if a == "流水號" and b and b != "課號" and not _is_table_header_token(b):
                serial = _normalize_dash_value(b) or serial
            if a == "課號" and b and b != "流水號" and not _is_table_header_token(b):
                code = _normalize_dash_value(b) or code

        if serial or code:
            break

    # (C) 四欄：流水號 值 課號 值
    if serial is None or code is None:
        for tr in driver.find_elements(By.CSS_SELECTOR, "main table tr, table tr"):
            tds = tr.find_elements(By.CSS_SELECTOR, "td, th")
            if len(tds) < 4:
                continue
            for j in range(len(tds) - 1):
                k = (tds[j].text or "").strip()
                v = (tds[j + 1].text or "").strip()
                if k == "流水號" and v and v != "課號":
                    serial = _normalize_dash_value(v) or serial
                if k == "課號" and v and v != "流水號":
                    code = _normalize_dash_value(v) or code

    return serial, code


def _extract_course_title(driver: webdriver.Chrome) -> str:
    """
    詳情頁主標題多為 main 內第一個 h6（最顯眼），其次才是 h1 / Typography。
    """
    xpaths = [
        "//main//h6[1]",
        "//main//*[contains(@class,'MuiTypography-h')][1]",
        "//main//h1[1]",
        "//article//h6[1]",
        "//h6[not(ancestor::nav)][1]",
        "//h1[not(ancestor::nav)][1]",
        "//*[contains(@class,'course-title')][1]",
    ]
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                t = (el.text or "").strip()
                if t and len(t) > 1 and "搜尋" not in t:
                    return t
        except Exception:
            continue
    return "N/A"


_DIM_LABELS = frozenset({"品質", "甜度", "涼度", "紮實"})


def _dimension_score_value(driver: webdriver.Chrome, dim: str) -> str | None:
    """
    四維分數：站方為內層 span（維度名）+ 外層 MuiTypography-body1 整段文字。
    優先 //span[contains(text(), dim)]/parent::span，再清掉維度名取得 5.0 或 ––。
    """
    others = _DIM_LABELS - {dim}
    parent_xpaths = (
        f"//span[contains(text(), '{dim}')]/parent::span[contains(@class, 'MuiTypography-body1')]",
        f"//span[contains(text(), '{dim}')]/parent::span",
    )
    for xp in parent_xpaths:
        try:
            el = driver.find_element(By.XPATH, xp)
            full = (el.text or "").strip()
            if not full:
                continue
            tail = full.replace(dim, "", 1).strip()
            while dim in tail:
                tail = tail.replace(dim, "", 1).strip()
            if not tail:
                return None
            if tail in ("--", "–", "—", "––", "~~"):
                return tail
            if any(ch.isdigit() for ch in tail) and len(tail) <= 12:
                return tail
        except Exception:
            continue

    xpaths = [
        f"//span[normalize-space()='{dim}']/following-sibling::span[1]",
        f"//span[contains(normalize-space(),'{dim}')]/following-sibling::*[1]",
        f"//*[normalize-space()='{dim}']/following-sibling::*[1]",
        f"//div[normalize-space()='{dim}']/following-sibling::div[1]",
        f"//*[normalize-space()='{dim}']/following-sibling::span[1]",
    ]
    for xp in xpaths:
        for el in driver.find_elements(By.XPATH, xp):
            t = (el.text or "").strip()
            if not t or t == dim:
                continue
            if t in others:
                continue
            if t in ("--", "–", "—", "~~", "––"):
                return t
            if any(ch.isdigit() for ch in t) and len(t) <= 12:
                return t
    try:
        block = driver.find_element(
            By.XPATH,
            f"//*[normalize-space()='{dim}']/ancestor::div[contains(@class,'flex')][1]",
        )
        for sp in block.find_elements(By.CSS_SELECTOR, "span, p"):
            t = (sp.text or "").strip()
            if not t or t == dim or t in others:
                continue
            if t in ("--", "–", "—", "––"):
                return t
            if any(ch.isdigit() for ch in t) and len(t) <= 12:
                return t
    except Exception:
        pass
    return None


def _scores_from_dimensions(driver: webdriver.Chrome) -> dict[str, str | None]:
    """四維平均分：不可誤抓隔壁欄的維度名稱當分數。"""
    dims = ("品質", "甜度", "涼度", "紮實")
    return {dim: _normalize_dash_value(_dimension_score_value(driver, dim)) for dim in dims}


def _scrape_detail(driver: webdriver.Chrome) -> dict:
    detail_wait = WebDriverWait(driver, DETAIL_PAGE_TIMEOUT)
    _wait_detail_ready(driver, detail_wait)

    try:
        WebDriverWait(driver, 12).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".MuiBackdrop-root"))
        )
    except TimeoutException:
        _dismiss_mui_backdrops(driver)

    short_wait = WebDriverWait(driver, 15)
    try:
        short_wait.until(EC.presence_of_element_located((By.TAG_NAME, "h6")))
    except TimeoutException:
        _save_detail_error_screenshot(driver, "no_h6")

    # 顯性等待：平均分數區塊（可選）
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//*[contains(normalize-space(.), '平均分數') or "
                    "contains(normalize-space(.), '品質')]",
                )
            )
        )
    except TimeoutException:
        pass

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 4);")
    time.sleep(0.25)

    course_name, prof = _extract_h6_title_and_professor(driver)
    item: dict = {
        "課名": course_name,
        "授課教授": _normalize_dash_value(prof) if prof else None,
        "開課系所": None,
        "學分": None,
        "最後開課學期": None,
        "流水號": None,
        "課號": None,
        "品質": None,
        "甜度": None,
        "涼度": None,
        "紮實": None,
        "評價內容": [],
        "評價明細_JSON": "[]",
    }

    for key, label in (
        ("開課系所", "開課系所"),
        ("學分", "學分數"),
        ("最後開課學期", "最後開課學期"),
    ):
        raw = _span_value_after_label(driver, label)
        if raw is None:
            raw = _text_by_label_pair(driver, label)
        item[key] = _normalize_dash_value(raw)

    if item["授課教授"] is None:
        raw = _span_value_after_label(driver, "授課教師") or _text_by_label_pair(driver, "授課教師")
        item["授課教授"] = _normalize_dash_value(raw)

    driver.execute_script("window.scrollTo(0, Math.max(0, document.body.scrollHeight - 400));")
    time.sleep(0.35)

    sn, cid = _table_serial_code_from_td(driver)
    if sn is None and cid is None:
        sn, cid = _parse_serial_and_course_id(driver)
    item["流水號"], item["課號"] = sn, cid

    try:
        WebDriverWait(driver, 10).until(
            EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "平均分數")
        )
    except TimeoutException:
        pass

    scores = _scores_from_dimensions(driver)
    item["品質"] = scores.get("品質")
    item["甜度"] = scores.get("甜度")
    item["涼度"] = scores.get("涼度")
    item["紮實"] = scores.get("紮實")

    if all(item[k] is None for k in ("品質", "甜度", "涼度", "紮實")):
        try:
            spans = driver.find_elements(
                By.XPATH,
                "//*[contains(normalize-space(.),'品質')]/ancestor::div[contains(@class,'flex')][1]"
                "//span[string-length(normalize-space())<=8]",
            )
            vals: list[str | None] = []
            for sp in spans[:24]:
                t = (sp.text or "").strip()
                if not t or t in _DIM_LABELS:
                    continue
                vals.append(_normalize_dash_value(t))
                if len(vals) >= 4:
                    break
            order = ("品質", "甜度", "涼度", "紮實")
            for i, dim in enumerate(order):
                if i < len(vals):
                    item[dim] = vals[i]
        except Exception:
            pass

    structured, readable = _scrape_reviews_block(driver)
    item["評價內容"] = readable
    item["評價明細_JSON"] = json.dumps(structured, ensure_ascii=False)

    return item


def _try_scrape_detail(driver: webdriver.Chrome) -> dict | None:
    """
    詳情頁連續失敗 DETAIL_MAX_RETRIES 次則略過該課程，回傳 None。
    （_scrape_detail 內已含 _wait_detail_ready，此處不重複等待。）
    """
    last_err: Exception | None = None
    for attempt in range(DETAIL_MAX_RETRIES):
        try:
            return _scrape_detail(driver)
        except TimeoutException as e:
            last_err = e
            _save_detail_error_screenshot(driver, f"timeout_attempt_{attempt + 1}")
            _maybe_human_scroll_detail(driver)
            _dismiss_mui_backdrops(driver)
            if not _body_has_meaningful_content(driver):
                _maybe_human_scroll_detail(driver)
            time.sleep(0.5 + random.uniform(0, 0.6))
            if attempt < DETAIL_MAX_RETRIES - 1:
                print(f"  詳情頁等待逾時，重試 {attempt + 2}/{DETAIL_MAX_RETRIES}…")
        except Exception as e:
            last_err = e
            _save_detail_error_screenshot(driver, f"scrape_error_attempt_{attempt + 1}")
            if attempt == DETAIL_MAX_RETRIES - 1:
                break
            time.sleep(0.4)
    if last_err:
        print(f"  已略過此課程（連續失敗 {DETAIL_MAX_RETRIES} 次）: {last_err}")
    return None


def scrape_ntu_rating() -> None:
    chrome_options = Options()
    chrome_options.add_argument(f"--user-agent={random.choice(_USER_AGENTS)}")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.page_load_strategy = "normal"

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(120)
    # 長時間爬蟲後頁面可能變慢；預設 script timeout 過短會讓 execute_script 拋錯
    driver.set_script_timeout(120)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
        )
    except Exception:
        pass

    wait = WebDriverWait(driver, LIST_PAGE_TIMEOUT)
    base_url = "https://rating.myntu.me/search/0?semester=114-2&strictSchedule=false"
    all_data: list[dict] = []
    current_page = 1
    limit_reached = False

    if MAX_COURSES_TOTAL is not None:
        print(
            f"試跑模式：最多抓取 {MAX_COURSES_TOTAL} 筆後結束。"
            " 若要全站爬取，請將 MAX_COURSES_TOTAL 改為 None。\n"
        )

    try:
        driver.get(base_url)
        time.sleep(1.0)
        _dismiss_overlays(driver)
        _dismiss_mui_backdrops(driver)

        while True:
            print(f"\n正在處理第 {current_page} 頁...")
            if current_page == 1:
                _click_search_button(driver, wait)
                time.sleep(2.0)
            _scroll_to_reveal_course_list(driver)

            if not _wait_list_ready(driver, wait):
                print("列表頁等待課程卡片超時（已用 a+h6 辨識）。")
                break

            cards = driver.find_elements(By.XPATH, COURSE_CARD_XPATH)
            n = len(cards)
            if n == 0:
                print("未取得課程卡片。")
                _debug_dump(driver, "no_course_cards")
                break

            print(f"本頁共 {n} 筆課程（同一分頁點擊 → 詳情 → 返回）。")

            abort_all = False
            for idx in range(n):
                anchors = driver.find_elements(By.XPATH, COURSE_CARD_XPATH)
                if idx >= len(anchors):
                    print(f"索引 {idx} 超出目前卡片數 {len(anchors)}，結束本頁。")
                    break
                el = anchors[idx]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.25)
                try:
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)

                try:
                    WebDriverWait(driver, 30).until(
                        lambda d: _is_course_detail_url(d.current_url)
                    )
                    _switch_to_latest_window_if_needed(driver)
                    item = _try_scrape_detail(driver)
                    if item is None:
                        print(f"略過 ({idx + 1}/{n})：詳情頁連續失敗。")
                    else:
                        all_data.append(item)
                        title_one_line = (item.get("課名") or "").replace("\n", " ").strip()
                        sn = item.get("流水號")
                        sn_log = str(sn) if sn else "（無）"
                        print(
                            f"已抓取 ({idx + 1}/{n}): {title_one_line} | 流水號: {sn_log}"
                        )
                        if (
                            MAX_COURSES_TOTAL is not None
                            and len(all_data) >= MAX_COURSES_TOTAL
                        ):
                            limit_reached = True
                except Exception as e:
                    print(f"詳情頁失敗: {e}")
                    if DEBUG:
                        traceback.print_exc()
                    _save_detail_error_screenshot(driver, "detail_exception_outer")
                    _debug_dump(driver, "detail_exception")
                finally:
                    if _is_course_detail_url(driver.current_url):
                        _leave_detail_return_to_list(driver)
                    elif len(driver.window_handles) > 1:
                        try:
                            driver.switch_to.window(driver.window_handles[-1])
                            if _is_course_detail_url(driver.current_url):
                                _leave_detail_return_to_list(driver)
                        except Exception:
                            pass
                    if "/search/" in driver.current_url:
                        try:
                            _wait_back_on_search_list(driver, wait)
                        except TimeoutException:
                            _debug_dump(driver, "back_to_list_timeout")
                            abort_all = True
                        else:
                            time.sleep(0.6)
                            _scroll_to_reveal_course_list(driver)
                if abort_all:
                    break
                if limit_reached:
                    print(f"\n已達試跑上限 {MAX_COURSES_TOTAL} 筆，提前結束。")
                    break

            if abort_all:
                print("返回搜尋列表失敗，停止爬取。")
                break
            if limit_reached:
                _ensure_data_dir()
                _write_rate_csv(all_data)
                break

            _ensure_data_dir()
            _write_rate_csv(all_data)

            try:
                _ensure_on_search_list(driver, base_url, wait)
                probe = _find_next_page_button(driver)
                if probe is None:
                    print("找不到下一頁按鈕（請確認目前是否在搜尋結果頁）。")
                    break
                if not probe.is_enabled():
                    print("已到最後一頁。")
                    break
                _click_next_page_button(driver)
                current_page += 1
                time.sleep(LIST_AFTER_PAGE_TURN_SLEEP)
                _scroll_to_reveal_course_list(driver)
            except TimeoutException as e:
                msg = str(e)
                if "最後一頁" in msg or "已停用" in msg:
                    print("已到最後一頁。")
                else:
                    print(f"翻頁失敗: {e}")
                    if DEBUG:
                        traceback.print_exc()
                        _debug_dump(driver, "pagination_fail")
                    break
            except Exception as e:
                print(f"翻頁失敗: {e}")
                if DEBUG:
                    traceback.print_exc()
                    _debug_dump(driver, "pagination_fail")
                break

    finally:
        driver.quit()
        print(f"\n任務結束，共抓取 {len(all_data)} 筆。輸出: {OUTPUT_CSV}")


if __name__ == "__main__":
    scrape_ntu_rating()
