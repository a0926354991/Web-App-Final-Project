"""
解析台大課程網的 schedule_time 字串。

常見格式:
  "四 10, A普303"       → [(4,'10'),(4,'A')]
  "五 3, 4綜603"        → [(5,'3'),(5,'4')]
  "三 A, B, C普102"     → [(3,'A'),(3,'B'),(3,'C')]
  "一 3, 4 三 7, 8外教" → [(1,'3'),(1,'4'),(3,'7'),(3,'8')]

無法 parse 的 (自由文字 "下午5:30", "每週一至週五全天" 等) 回傳 []。

weekday: 一=1, 二=2, ..., 日=7
period: '1'-'10' 或 'A'-'D'
"""

from __future__ import annotations

import re

WEEKDAY_CHARS = "一二三四五六日"


def parse_schedule(s: str | None) -> list[tuple[int, str]]:
    """回傳 [(weekday, period), ...]，無法 parse 的回空 list。"""
    if not s:
        return []
    # 統一前綴:把「星期X」「週X」標準化成單字 X
    # 例: '星期一1,2' → '一1,2', '週五 3,4' → '五 3,4'
    normalized = re.sub(r"(?:星期|週)([一二三四五六日])", r"\1", s)
    s = normalized

    slots: list[tuple[int, str]] = []
    # 找出所有 weekday 字元的位置
    weekday_hits = [
        (m.start(), WEEKDAY_CHARS.index(m.group()) + 1)
        for m in re.finditer(rf"[{WEEKDAY_CHARS}]", s)
    ]
    for i, (pos, wd) in enumerate(weekday_hits):
        end = weekday_hits[i + 1][0] if i + 1 < len(weekday_hits) else len(s)
        segment = s[pos + 1 : end].strip()
        # 從 segment 開頭依序抓 period token,中間只能是 , 空白 - ~
        # 一遇到非 period / 非分隔符 (例如中文地點) 就停
        m = re.match(
            r"((?:[0-9]+|[A-D])(?:[,，\s\-~～]+(?:[0-9]+|[A-D]))*)",
            segment,
        )
        if m:
            tokens = re.findall(r"[0-9]+|[A-D]", m.group(1))
            slots.extend((wd, t) for t in tokens)
    return slots


def slots_conflict(a: list[tuple[int, str]], b: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """回傳衝堂的 (weekday, period)。"""
    return sorted(set(a) & set(b))


# 簡單測試:python -m backend.api.schedule
if __name__ == "__main__":
    tests = [
        "四 10, A普303",
        "五 3, 4綜603",
        "三 A, B, C普102",
        "三 6, 7普302",
        "二 5, 6共105",
        "一 3, 4 三 7, 8外教103",
        "下午5:30~6:30",
        "每週一至週五全天。與郭彥彬合授",
        "",
        "星期一1,2",
        "星期五2,3,4",
        "週五上午10:20-12:30",
        "每週一、三 08:30 – 10:00 AM",
    ]
    for t in tests:
        print(f"{t!r:40s} → {parse_schedule(t)}")
