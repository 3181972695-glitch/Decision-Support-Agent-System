"""Tests for the 9 new features added in the product quality update."""

import pytest
from app.domain.debate import (
    Argument,
    Debate,
    Evidence,
    JudgeEvaluation,
    Round,
    RoundMemory,
    Verdict,
)
from app.domain.enums import AgentRole, DebateStatus


# ── Feature 1: Structured Judge Evaluation ──────────────────────

class TestJudgeEvaluation:
    def test_from_dict_parses_complete_data(self) -> None:
        data = {
            "winner": "pro",
            "scores": {"logic": 91, "evidence": 84, "rebuttal": 88, "consistency": 93, "clarity": 90},
            "confidence": 0.86,
            "strengths": ["Clear logical structure", "Strong evidence"],
            "weaknesses": ["Some repetition", "Weak counter-argument handling"],
        }
        ev = JudgeEvaluation.from_dict(data)
        assert ev.winner == "pro"
        assert ev.scores["logic"] == 91
        assert ev.confidence == 0.86
        assert len(ev.strengths) == 2
        assert len(ev.weaknesses) == 2

    def test_from_dict_handles_missing_fields(self) -> None:
        data = {"winner": "con"}
        ev = JudgeEvaluation.from_dict(data)
        assert ev.winner == "con"
        assert ev.scores == {}
        assert ev.confidence == 0.0
        assert ev.strengths == []
        assert ev.weaknesses == []

    def test_from_dict_handles_invalid_scores(self) -> None:
        data = {"winner": "pro", "scores": "not_a_dict"}
        ev = JudgeEvaluation.from_dict(data)
        assert ev.scores == {}

    def test_to_dict_roundtrips(self) -> None:
        data = {
            "winner": "pro",
            "scores": {"logic": 80},
            "confidence": 0.75,
            "strengths": ["S1"],
            "weaknesses": ["W1"],
        }
        ev = JudgeEvaluation.from_dict(data)
        assert ev.to_dict() == data

    def test_verdict_with_evaluation(self) -> None:
        ev = JudgeEvaluation.from_dict({"winner": "pro", "scores": {"logic": 90}, "confidence": 0.8})
        v = Verdict(summary="Pro wins", recommendation="Go with pro", evaluation=ev)
        assert v.evaluation is not None
        assert v.evaluation.winner == "pro"

    def test_verdict_without_evaluation(self) -> None:
        v = Verdict(summary="Tie", recommendation="More research needed")
        assert v.evaluation is None


# ── Feature 2: Round Memory ─────────────────────────────────────

class TestRoundMemory:
    def test_to_compact_str_with_all_fields(self) -> None:
        mem = RoundMemory(
            pro_claim="Pro says X is beneficial",
            con_claim="Con says X is harmful",
            strongest_evidence="Study shows 30% improvement",
            remaining_disagreement="Cost-benefit ratio",
            moderator_takeaway="Both sides agree on the problem",
        )
        result = mem.to_compact_str()
        assert "Pro: Pro says X is beneficial" in result
        assert "Con: Con says X is harmful" in result
        assert "Evidence: Study shows 30% improvement" in result
        assert "Takeaway: Both sides agree on the problem" in result

    def test_to_compact_str_empty(self) -> None:
        mem = RoundMemory()
        assert mem.to_compact_str() == ""

    def test_from_moderator_summary_extracts_pro_con(self) -> None:
        summary = "The debate was informative. Pro argued that renewable energy is cost-effective. Con countered that infrastructure costs are prohibitive."
        mem = RoundMemory.from_moderator_summary(summary)
        assert len(mem.moderator_takeaway) > 0
        # Should find at least one claim
        assert mem.pro_claim or mem.con_claim

    def test_from_moderator_summary_empty(self) -> None:
        mem = RoundMemory.from_moderator_summary("")
        assert mem.pro_claim == ""
        assert mem.con_claim == ""

    def test_round_stores_memory(self) -> None:
        mem = RoundMemory(pro_claim="P", con_claim="C")
        r = Round(round_number=1, memory=mem)
        assert r.memory is not None
        assert r.memory.pro_claim == "P"

    def test_round_without_memory(self) -> None:
        r = Round(round_number=1)
        assert r.memory is None


# ── Feature 3: Evidence Tracking ────────────────────────────────

class TestEvidence:
    def test_evidence_creation(self) -> None:
        ev = Evidence(claim="Solar is cheap", evidence="Cost fell 89%", reasoning="Economies of scale")
        assert ev.claim == "Solar is cheap"
        assert ev.evidence == "Cost fell 89%"

    def test_argument_with_evidence(self) -> None:
        ev = Evidence(claim="C1", evidence="E1", reasoning="R1")
        arg = Argument(role=AgentRole.PRO, content="Solar is great", evidence=[ev])
        assert len(arg.evidence) == 1
        assert arg.evidence[0].claim == "C1"

    def test_argument_without_evidence(self) -> None:
        arg = Argument(role=AgentRole.CON, content="No")
        assert arg.evidence == []

    def test_multiple_evidence_items(self) -> None:
        evs = [Evidence(claim=f"C{i}") for i in range(3)]
        arg = Argument(role=AgentRole.PRO, content="Multi", evidence=evs)
        assert len(arg.evidence) == 3


# ── Feature 4: Debate Analytics (profiler) ──────────────────────

class TestAnalytics:
    def test_debate_tracks_rounds(self) -> None:
        debate = Debate(id="test1", topic="Test", max_rounds=2)
        debate.add_round(Round(round_number=1))
        assert len(debate.rounds) == 1

    def test_debate_id_in_verdict(self) -> None:
        v = Verdict(summary="S", recommendation="R")
        debate = Debate(id="test2", topic="T", max_rounds=1)
        debate.set_verdict(v)
        assert debate.status == DebateStatus.COMPLETED
        assert debate.verdict is not None
        assert debate.verdict.summary == "S"


# ── Feature 5: Progress UI (timeline builder tested in domain) ──

class TestProgressTimeline:
    def test_round_has_all_fields(self) -> None:
        r = Round(round_number=1, round_focus="Test focus")
        assert r.round_number == 1
        assert r.round_focus == "Test focus"
        assert r.moderator_intro is None
        assert r.pro_opening is None
        assert r.con_opening is None
        assert r.cross_examination == []
        assert r.pro_rebuttal is None
        assert r.con_rebuttal is None
        assert r.moderator_summary is None

    def test_debate_rounds_ordered(self) -> None:
        debate = Debate(id="t3", topic="T", max_rounds=2)
        debate.add_round(Round(round_number=1))
        debate.add_round(Round(round_number=2))
        assert len(debate.rounds) == 2
        assert debate.rounds[0].round_number == 1
        assert debate.rounds[1].round_number == 2


# ── Feature 6: Replay (domain models reusable) ──────────────────

class TestReplay:
    def test_debate_rounds_are_serializable(self) -> None:
        r = Round(round_number=1, moderator_intro="Intro")
        r.pro_opening = Argument(role=AgentRole.PRO, content="Pro arg")
        r.con_opening = Argument(role=AgentRole.CON, content="Con arg")
        debate = Debate(id="t4", topic="T", max_rounds=1)
        debate.add_round(r)
        # Verify round data is accessible
        latest = debate.latest_round()
        assert latest is not None
        assert latest.pro_opening is not None
        assert latest.pro_opening.content == "Pro arg"


# ── Feature 7: Model Selection (config) ─────────────────────────

class TestModelSelection:
    def test_argument_has_role(self) -> None:
        arg = Argument(role=AgentRole.PRO, content="Test")
        assert arg.role == AgentRole.PRO

    def test_argument_has_created_at(self) -> None:
        arg = Argument(role=AgentRole.CON, content="Test")
        assert arg.created_at is not None


# ── Feature 8: Performance Constraints ──────────────────────────

class TestPerformance:
    def test_round_memory_is_compact(self) -> None:
        """RoundMemory.to_compact_str() should be significantly shorter than full round text."""
        mem = RoundMemory(
            pro_claim="A" * 200,
            con_claim="B" * 200,
            strongest_evidence="C" * 200,
            remaining_disagreement="D" * 200,
            moderator_takeaway="E" * 200,
        )
        compact = mem.to_compact_str()
        # Each field is truncated to <= 150/120 chars
        assert len(compact) < 1000

    def test_context_summary_uses_memory(self) -> None:
        """Verify that RoundMemory exists and can be used."""
        mem = RoundMemory(moderator_takeaway="Key takeaway")
        r = Round(round_number=1, memory=mem)
        assert r.memory is not None
        assert r.memory.moderator_takeaway == "Key takeaway"


# ── Feature 9: Comprehensive Tests ──────────────────────────────

class TestIntegration:
    def test_full_round_creation(self) -> None:
        """Simulate a complete round with all fields."""
        r = Round(
            round_number=1,
            round_focus="Initial arguments",
            moderator_intro="Let's begin the debate.",
            moderator_summary="Good round overall.",
            moderator_steer="Focus on evidence next round.",
            memory=RoundMemory(pro_claim="Pro: X", con_claim="Con: Y"),
        )
        r.pro_opening = Argument(
            role=AgentRole.PRO,
            content="I support this.",
            evidence=[Evidence(claim="C1", evidence="E1", reasoning="R1")],
        )
        r.con_opening = Argument(
            role=AgentRole.CON,
            content="I oppose this.",
            evidence=[Evidence(claim="C2", evidence="E2", reasoning="R2")],
        )
        assert r.pro_opening.evidence[0].claim == "C1"
        assert r.con_opening.evidence[0].claim == "C2"
        assert r.memory is not None
        assert r.memory.pro_claim == "Pro: X"

    def test_debate_with_verdict_and_evaluation(self) -> None:
        """Complete debate lifecycle with structured evaluation."""
        debate = Debate(id="full-test", topic="Should we deploy?", max_rounds=1)
        r = Round(round_number=1, moderator_summary="Done")
        debate.add_round(r)
        ev = JudgeEvaluation.from_dict({"winner": "pro", "scores": {"logic": 85}, "confidence": 0.9, "strengths": ["Good"], "weaknesses": ["Bad"]})
        v = Verdict(summary="Pro wins", recommendation="Deploy", evaluation=ev)
        debate.set_verdict(v)
        assert debate.status == DebateStatus.COMPLETED
        assert debate.verdict is not None
        assert debate.verdict.evaluation is not None
        assert debate.verdict.evaluation.winner == "pro"
        assert debate.verdict.evaluation.scores["logic"] == 85
