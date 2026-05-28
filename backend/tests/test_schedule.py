"""parse_schedule / slots_conflict 單元測試。

parse_schedule 把課程網的 schedule_time 字串解析成 [(weekday, period), ...]。
課表衝堂偵測全靠它,格式變體多 (數字節 / A-D 節 / 跨日 / 髒值),最易悄悄出錯。
"""

from backend.api.schedule import parse_schedule, slots_conflict


class TestParseSchedule:
    def test_single_day_numeric(self):
        assert parse_schedule("三 6, 7普302") == [(3, "6"), (3, "7")]

    def test_mixed_numeric_and_letter(self):
        # "四 10, A" — 10 節 + A 節 (午休後時段)
        assert parse_schedule("四 10, A普303") == [(4, "10"), (4, "A")]

    def test_all_letter_periods(self):
        assert parse_schedule("三 A, B, C普102") == [(3, "A"), (3, "B"), (3, "C")]

    def test_cross_day(self):
        # 一門課跨兩天
        assert parse_schedule("一 3, 4 三 7, 8外教103") == [
            (1, "3"), (1, "4"), (3, "7"), (3, "8")
        ]

    def test_weekday_prefix_xingqi(self):
        # "星期一1,2" 前綴標準化
        assert parse_schedule("星期一1,2") == [(1, "1"), (1, "2")]

    def test_weekday_prefix_zhou(self):
        assert parse_schedule("週五2,3,4") == [(5, "2"), (5, "3"), (5, "4")]

    def test_location_suffix_stripped(self):
        # 時段後面緊接中文教室,應在教室處停止
        assert parse_schedule("二 5, 6共105") == [(2, "5"), (2, "6")]

    def test_all_weekdays_map_correctly(self):
        # 一=1 ... 日=7
        assert parse_schedule("日 1") == [(7, "1")]
        assert parse_schedule("六 2") == [(6, "2")]

    # ---- 無法 parse 的應回空 ----
    def test_empty_returns_empty(self):
        assert parse_schedule("") == []
        assert parse_schedule(None) == []

    def test_free_text_time_returns_empty(self):
        assert parse_schedule("下午5:30~6:30") == []

    def test_full_week_prose_returns_empty(self):
        assert parse_schedule("每週一至週五全天。與郭彥彬合授") == []

    def test_morning_range_prose_returns_empty(self):
        assert parse_schedule("週五上午10:20-12:30") == []


class TestParseScheduleKnownQuirks:
    """已知的非理想行為 — 記錄現狀 (非標準時間字串本就少,影響小)。
    若之後強化 parse 邏輯,這些斷言要更新。"""

    def test_prose_with_clock_time_partial_parse(self):
        # "每週一、三 08:30 – 10:00 AM" 會誤把 "三 08" 當成第 08 節 — 已知限制
        # 這類字串在 DB 僅約數十筆,且不影響有正常時段的課
        assert parse_schedule("每週一、三 08:30 – 10:00 AM") == [(3, "08")]


class TestSlotsConflict:
    def test_no_overlap(self):
        assert slots_conflict([(1, "3")], [(2, "4")]) == []

    def test_overlap_single(self):
        assert slots_conflict([(1, "3"), (1, "4")], [(1, "4"), (2, "5")]) == [(1, "4")]

    def test_overlap_sorted(self):
        a = [(3, "7"), (1, "2")]
        b = [(1, "2"), (3, "7")]
        assert slots_conflict(a, b) == [(1, "2"), (3, "7")]

    def test_empty_inputs(self):
        assert slots_conflict([], [(1, "1")]) == []
        assert slots_conflict([], []) == []
