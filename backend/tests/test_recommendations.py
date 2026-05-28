"""適合度演算法單元測試 — compute_fit 與各成份。

這是 app 的核心賣點:5 成份加權算「適合度」。純數值邏輯,最易悄悄算錯。
compute_interest_score / compute_ability_score 依賴模組級 _CACHE (正常由
init_indices 從 DB 建);測試用 fixture 直接 populate _CACHE,隔離 DB。
"""

import re

import pytest

from backend.api import recommendations as rec


@pytest.fixture
def profile():
    """中性 profile:能力全 60,偏好甜度 70 / loading 30,興趣含 AI。"""
    return {
        "ability_logic": 80, "ability_writing": 40, "ability_coding": 90,
        "ability_humanities": 30, "ability_teamwork": 50,
        "pref_sweetness": 70, "pref_loading": 30,
        "interests": ["AI", "程式"],
    }


@pytest.fixture(autouse=True)
def fake_indices(monkeypatch):
    """塞一個小的 _CACHE,模擬 init_indices 的產物,不碰 DB。

    兩門課:
      ('114-2','11111') = 一門 AI/程式課 (課名命中 AI + 程式關鍵字)
      ('114-2','22222') = 一門純人文課 (不命中興趣 tag)
    """
    key_ai = ("114-2", "11111")
    key_hum = ("114-2", "22222")

    text_index = {
        key_ai: {"name": "人工智慧 AI 與程式設計", "dept": "資訊工程學系",
                 "obj": "學習 AI 演算法與程式實作", "ov": "Python 程式 機器學習"},
        key_hum: {"name": "中國哲學史", "dept": "哲學系",
                  "obj": "探討先秦思想", "ov": "儒家 道家 倫理"},
    }
    # ability_profile: 課程所需能力的 weight (0-100)
    ability_profile = {
        key_ai: {"coding": 100, "logic": 100},  # 需 coding + logic
        key_hum: {"humanities": 100},            # 需 humanities
    }
    interest_tags = {key_ai: {"AI", "程式"}, key_hum: set()}
    tag_patterns = {tag: rec._compile_tag_pattern(tag) for tag in rec.INTEREST_TAGS_ALL}
    # IDF: 給 AI / 程式 一個正值權重 (越稀有越高)
    idf = {tag: 1.0 for tag in rec.INTEREST_TAGS_ALL}

    monkeypatch.setitem(rec._CACHE, "text_index", text_index)
    monkeypatch.setitem(rec._CACHE, "ability_profile", ability_profile)
    monkeypatch.setitem(rec._CACHE, "interest_tags", interest_tags)
    monkeypatch.setitem(rec._CACHE, "tag_patterns", tag_patterns)
    monkeypatch.setitem(rec._CACHE, "idf", idf)
    monkeypatch.setitem(rec._CACHE, "ready", True)
    # 關掉 LLM,explanation 走 template
    monkeypatch.setattr(rec.llm, "is_available", lambda: False)
    return {"ai": key_ai, "hum": key_hum}


class TestInterestScore:
    def test_matches_interest_scores_positive(self, profile, fake_indices):
        score, matched = rec.compute_interest_score(profile, fake_indices["ai"])
        assert score > 0
        assert set(matched) == {"AI", "程式"}

    def test_no_match_scores_zero(self, profile, fake_indices):
        score, matched = rec.compute_interest_score(profile, fake_indices["hum"])
        assert score == 0.0
        assert matched == []

    def test_no_interests_returns_neutral(self, fake_indices):
        p = {"interests": []}
        score, matched = rec.compute_interest_score(p, fake_indices["ai"])
        assert score == 50.0
        assert matched == []

    def test_score_capped_at_100(self, profile, fake_indices):
        score, _ = rec.compute_interest_score(profile, fake_indices["ai"])
        assert score <= 100.0


class TestAbilityScore:
    def test_weighted_average_of_required(self, profile, fake_indices):
        # AI 課需 coding(90) + logic(80) → 平均 85
        score, required = rec.compute_ability_score(profile, fake_indices["ai"])
        assert score == pytest.approx(85.0)
        assert set(required) == {"coding", "logic"}

    def test_single_required_ability(self, profile, fake_indices):
        # 人文課需 humanities(30)
        score, required = rec.compute_ability_score(profile, fake_indices["hum"])
        assert score == pytest.approx(30.0)
        assert required == ["humanities"]

    def test_no_required_returns_neutral(self, profile):
        # 不在 ability_profile 的課 → 中性 50
        score, required = rec.compute_ability_score(profile, ("114-2", "99999"))
        assert score == 50.0
        assert required == []


class TestComputeFit:
    def test_total_is_weighted_sum(self, profile, fake_indices):
        # 給定 stats,驗證 total = 各成份 × 權重
        stats = {"avg_rec": 4.0, "avg_sweet": 3.5, "avg_workload": 1.5, "n_reviews": 10}
        fit = rec.compute_fit(profile, stats, fake_indices["ai"])

        # rec = 4.0*20 = 80
        assert fit["recommendation"] == pytest.approx(80.0)
        # sweet = 100 - |70 - 3.5*20| = 100 - 0 = 100
        assert fit["sweetness"] == pytest.approx(100.0)
        # load = 100 - |30 - 1.5*20| = 100 - 0 = 100
        assert fit["loading"] == pytest.approx(100.0)

        expected_total = (
            rec.WEIGHT_REC * fit["recommendation"]
            + rec.WEIGHT_SWEET * fit["sweetness"]
            + rec.WEIGHT_LOAD * fit["loading"]
            + rec.WEIGHT_INTEREST * fit["interest"]
            + rec.WEIGHT_ABILITY * fit["ability"]
        )
        assert fit["total"] == pytest.approx(round(expected_total, 1))

    def test_no_stats_uses_neutral_50(self, profile, fake_indices):
        # stats=None → 前 3 成份 (rec/sweet/load) 都用中性 50
        fit = rec.compute_fit(profile, None, fake_indices["ai"])
        assert fit["recommendation"] == 50.0
        assert fit["sweetness"] == 50.0
        assert fit["loading"] == 50.0
        assert fit["n_reviews"] == 0

    def test_sweetness_penalises_distance(self, profile, fake_indices):
        # 偏好甜度 70,但課程甜度均值 1.0*20=20 → diff 50 → score 50
        stats = {"avg_rec": 3.0, "avg_sweet": 1.0, "avg_workload": 1.5, "n_reviews": 5}
        fit = rec.compute_fit(profile, stats, fake_indices["ai"])
        assert fit["sweetness"] == pytest.approx(50.0)

    def test_sweetness_floors_at_zero(self, profile, fake_indices):
        # 極端不匹配不會變負
        p = {**profile, "pref_sweetness": 100}
        stats = {"avg_rec": 3.0, "avg_sweet": 0.0, "avg_workload": 1.5, "n_reviews": 5}
        fit = rec.compute_fit(p, stats, fake_indices["ai"])
        assert fit["sweetness"] >= 0.0

    def test_fit_has_explanation(self, profile, fake_indices):
        # LLM 關掉 → 應 fallback template explanation (非空)
        fit = rec.compute_fit(profile, None, fake_indices["ai"], use_llm=True)
        assert isinstance(fit["explanation"], str)
        assert fit["explanation"]


class TestSemanticBoost:
    """top-N 重排的 embedding 語意加成 — 把 ai_features.semantic_interest_score
    mock 掉,只驗證混合公式與 fallback,不真的呼叫 Gemini。"""

    def test_blend_with_tfidf(self, profile, fake_indices, monkeypatch):
        # semantic 回 80,TF-IDF 原本某值 → 混合 (各半)
        monkeypatch.setattr(
            "backend.api.ai_features.semantic_interest_score",
            lambda interests, text: 80.0,
        )
        tfidf_only, _ = rec.compute_interest_score(profile, fake_indices["ai"])
        boosted = rec._maybe_semantic_boost(profile, fake_indices["ai"], tfidf_only)
        expected = round(0.5 * 80.0 + 0.5 * tfidf_only, 1)
        assert boosted == pytest.approx(expected)

    def test_fallback_when_semantic_none(self, profile, fake_indices, monkeypatch):
        # embedding 失敗 (回 None) → 維持純 TF-IDF
        monkeypatch.setattr(
            "backend.api.ai_features.semantic_interest_score",
            lambda interests, text: None,
        )
        boosted = rec._maybe_semantic_boost(profile, fake_indices["ai"], 42.0)
        assert boosted == 42.0

    def test_no_interests_skips_semantic(self, fake_indices, monkeypatch):
        called = {"n": 0}

        def _spy(interests, text):
            called["n"] += 1
            return 90.0
        monkeypatch.setattr("backend.api.ai_features.semantic_interest_score", _spy)
        # 沒興趣 → 不該呼叫 embedding (省 API)
        rec._maybe_semantic_boost({"interests": []}, fake_indices["ai"], 50.0)
        assert called["n"] == 0

    def test_compute_fit_use_semantic_changes_interest(self, profile, fake_indices, monkeypatch):
        # use_semantic=True 時 interest 分數應反映 blend
        monkeypatch.setattr(
            "backend.api.ai_features.semantic_interest_score",
            lambda interests, text: 100.0,
        )
        plain = rec.compute_fit(profile, None, fake_indices["ai"])
        boosted = rec.compute_fit(profile, None, fake_indices["ai"], use_semantic=True)
        # semantic=100 應把興趣分往上拉 (除非 TF-IDF 本來就 100)
        assert boosted["interest"] >= plain["interest"]


class TestTagPattern:
    def test_ascii_tag_word_boundary(self):
        # AI 用詞邊界,不應命中 "main" / "again"
        pat = rec._compile_tag_pattern("AI")
        assert pat.search("AI 課程")
        assert not pat.search("again maintain")

    def test_chinese_tag_substring(self):
        pat = rec._compile_tag_pattern("程式")
        assert pat.search("程式設計")
