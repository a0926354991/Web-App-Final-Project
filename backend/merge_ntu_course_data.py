"""
合併 NTU Rating 評價檔 (ntu_rate_data.csv) 與台大課程介紹檔 (ntu_detailed_data.csv)。

複合鍵：流水號 + 課號。預設以評價檔為左表 (left join)，每列評價對應一筆課程網資料。
介紹檔若同一 (流水號, 課號) 多列，只保留第一列。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

_KEY_COLS = ("流水號", "課號")


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_data_dir() -> Path:
    return _backend_dir() / "data"


def _normalize_serial(series: pd.Series) -> pd.Series:
    """流水號：統一為整數字串，避免 float 讀成 43414.0 與 43414 無法合併。"""
    num = pd.to_numeric(series, errors="coerce")
    int_str = num.astype("Int64").astype("string").replace("<NA>", "")
    fallback = series.astype("string").fillna("").str.strip()
    return int_str.where(num.notna(), fallback)


def _normalize_course_code(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def _normalize_keys(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """將流水號、課號轉成可比對的字串（流水號整數化；課號 strip）。"""
    out = df.copy()
    if "流水號" not in out.columns or "課號" not in out.columns:
        raise ValueError(f"{prefix}: 缺少欄位 {_KEY_COLS!r}")
    out["流水號"] = _normalize_serial(out["流水號"])
    out["課號"] = _normalize_course_code(out["課號"])
    return out


def merge_course_data(
    rate_path: Path,
    detail_path: Path,
    output_path: Path,
    unmatched_path: Path | None = None,
) -> tuple[int, int, int]:
    """
    讀取兩 CSV、合併、寫出。

    回傳 (評價列數, 成功對到介紹檔列數, 未對到列數)。
    """
    rate = pd.read_csv(rate_path, encoding="utf-8-sig")
    detail = pd.read_csv(detail_path, encoding="utf-8-sig")

    rate = _normalize_keys(rate, "評價檔")
    detail = _normalize_keys(detail, "介紹檔")

    n_detail_before = len(detail)
    detail = detail.drop_duplicates(subset=list(_KEY_COLS), keep="first")
    n_dup = n_detail_before - len(detail)
    if n_dup:
        print(f"介紹檔依 (流水號, 課號) 去重：移除 {n_dup} 筆重複列。")

    merged = pd.merge(
        rate,
        detail,
        on=list(_KEY_COLS),
        how="left",
        suffixes=("", "_catalog"),
        indicator=True,
    )

    unmatched_mask = merged["_merge"] == "left_only"
    n_rate = len(rate)
    n_unmatched = int(unmatched_mask.sum())
    n_matched = n_rate - n_unmatched

    print(f"評價檔列數: {n_rate}")
    print(f"與介紹檔成功對應: {n_matched}")
    print(f"介紹檔中找不到鍵: {n_unmatched}")

    out = merged.drop(columns=["_merge"], errors="ignore")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
        na_rep="",
        quoting=csv.QUOTE_MINIMAL,
    )
    print(f"已寫入: {output_path}")

    if unmatched_path is not None and n_unmatched > 0:
        um = merged.loc[unmatched_mask, list(_KEY_COLS)].drop_duplicates()
        unmatched_path.parent.mkdir(parents=True, exist_ok=True)
        um.to_csv(
            unmatched_path,
            index=False,
            encoding="utf-8-sig",
            na_rep="",
        )
        print(f"未匹配鍵已寫入: {unmatched_path}")

    return n_rate, n_matched, n_unmatched


def main() -> None:
    data = _default_data_dir()
    parser = argparse.ArgumentParser(description="合併 ntu_rate_data 與 ntu_detailed_data（鍵：流水號+課號）")
    parser.add_argument(
        "--rate",
        type=Path,
        default=data / "ntu_rate_data.csv",
        help="評價 CSV 路徑",
    )
    parser.add_argument(
        "--detail",
        type=Path,
        default=data / "ntu_detailed_data.csv",
        help="課程介紹 CSV 路徑",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=data / "ntu_merged.csv",
        help="合併輸出 CSV",
    )
    parser.add_argument(
        "--unmatched-output",
        type=Path,
        default=None,
        help="可選：將未在介紹檔對到的 (流水號, 課號) 寫入此 CSV",
    )
    parser.add_argument(
        "--write-unmatched",
        action="store_true",
        help="寫入未匹配鍵到 data/ntu_merge_unmatched_keys.csv（可與 --unmatched-output 擇一或併用覆寫路徑）",
    )
    args = parser.parse_args()

    if args.unmatched_output is not None:
        unmatched: Path | None = args.unmatched_output
    elif args.write_unmatched:
        unmatched = data / "ntu_merge_unmatched_keys.csv"
    else:
        unmatched = None

    merge_course_data(
        args.rate,
        args.detail,
        args.output,
        unmatched_path=unmatched,
    )


if __name__ == "__main__":
    main()
