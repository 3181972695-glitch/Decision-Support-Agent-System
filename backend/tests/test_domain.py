"""Comprehensive tests for the pure domain layer.

All tests in this module verify domain behaviour in isolation —
no infrastructure, no LLM, no FastAPI.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.debate import (
    Argument,
    CrossExaminationQA,
    Debate,
    Round,
    UserQuestionQA,
    Verdict,
)
from app.domain.enums import AgentRole, DebateStatus


# =================================================================
#  Argument
# =================================================================


class TestArgument:
    """Argument is a value object holding a single agent's argument."""

    def test_create_with_role_and_content(self) -> None:
        arg = Argument(role=AgentRole.PRO, content="Graduate school builds expertise.")
        assert arg.role == AgentRole.PRO
        assert arg.content == "Graduate school builds expertise."

    def test_created_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(timezone.utc)
        arg = Argument(role=AgentRole.CON, content="Debt is a concern.")
        after = datetime.now(timezone.utc)
        assert before <= arg.created_at <= after

    def test_created_at_can_be_set_explicitly(self) -> None:
        fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
        arg = Argument(
            role=AgentRole.PRO,
            content="Advanced degrees increase lifetime earnings.",
            created_at=fixed,
        )
        assert arg.created_at == fixed

    def test_two_arguments_with_same_fields_have_different_identity(self) -> None:
        arg_a = Argument(role=AgentRole.PRO, content="Point A.")
        arg_b = Argument(role=AgentRole.PRO, content="Point A.")
        assert arg_a is not arg_b

    @pytest.mark.parametrize("role", [AgentRole.PRO, AgentRole.CON])
    def test_all_agent_roles_are_accepted(self, role: AgentRole) -> None:
        arg = Argument(role=role, content="Some argument.")
        assert arg.role == role


# =================================================================
#  CrossExaminationQA
# =================================================================


class TestCrossExaminationQA:
    """CrossExaminationQA holds a Q&A pair between opposing agents."""

    def test_create_qa_pair(self) -> None:
        qa = CrossExaminationQA(
            question_role=AgentRole.PRO,
            question="What evidence supports your claim?",
            answer_role=AgentRole.CON,
            answer="The evidence is clear.",
        )
        assert qa.question_role == AgentRole.PRO
        assert qa.question == "What evidence supports your claim?"
        assert qa.answer_role == AgentRole.CON
        assert qa.answer == "The evidence is clear."


# =================================================================
#  UserQuestionQA
# =================================================================


class TestUserQuestionQA:
    """UserQuestionQA holds a user's question and an agent's answer."""

    def test_create_user_qa(self) -> None:
        uq = UserQuestionQA(
            target_role=AgentRole.PRO,
            question="How does this apply to my situation?",
            answer="Consider your specific circumstances.",
        )
        assert uq.target_role == AgentRole.PRO
        assert uq.question == "How does this apply to my situation?"
        assert uq.answer == "Consider your specific circumstances."


# =================================================================
#  Round
# =================================================================


class TestRound:
    """Round is an entity holding one round of the debate."""

    def test_create_with_required_fields(self) -> None:
        round_ = Round(round_number=1)
        assert round_.round_number == 1
        assert round_.round_focus is None
        assert round_.moderator_intro is None
        assert round_.pro_opening is None
        assert round_.con_opening is None
        assert round_.cross_examination == []
        assert round_.pro_rebuttal is None
        assert round_.con_rebuttal is None
        assert round_.user_questions == []
        assert round_.moderator_summary is None
        assert round_.moderator_steer is None
        # Legacy compat

    def test_create_with_all_fields(self) -> None:
        pro = Argument(role=AgentRole.PRO, content="For it.")
        con = Argument(role=AgentRole.CON, content="Against it.")
        pro_rebuttal = Argument(role=AgentRole.PRO, content="Rebuttal.")
        con_rebuttal = Argument(role=AgentRole.CON, content="Counter.")
        cross = [
            CrossExaminationQA(
                question_role=AgentRole.PRO,
                question="Why?",
                answer_role=AgentRole.CON,
                answer="Because.",
            )
        ]
        round_ = Round(
            round_number=2,
            round_focus="Challenge assumptions",
            moderator_intro="Let's discuss costs.",
            pro_opening=pro,
            con_opening=con,
            cross_examination=cross,
            pro_rebuttal=pro_rebuttal,
            con_rebuttal=con_rebuttal,
            moderator_summary="Both sides raised valid points.",
            moderator_steer="Focus on financial aspects next round.",
        )
        assert round_.round_number == 2
        assert round_.round_focus == "Challenge assumptions"
        assert round_.moderator_intro == "Let's discuss costs."
        assert round_.pro_opening is pro
        assert round_.con_opening is con
        assert len(round_.cross_examination) == 1
        assert round_.pro_rebuttal is pro_rebuttal
        assert round_.con_rebuttal is con_rebuttal

    def test_round_number_accepts_any_integer_by_default(self) -> None:
        round_ = Round(round_number=0)
        assert round_.round_number == 0
        round_ = Round(round_number=-1)
        assert round_.round_number == -1

    def test_user_questions_can_be_added(self) -> None:
        round_ = Round(round_number=1)
        uq = UserQuestionQA(
            target_role=AgentRole.PRO,
            question="User question?",
            answer="Agent answer.",
        )
        round_.user_questions.append(uq)
        assert len(round_.user_questions) == 1
        assert round_.user_questions[0].question == "User question?"


# =================================================================
#  Verdict
# =================================================================


class TestVerdict:
    """Verdict is a value object holding the judge's final decision."""

    def test_create_with_summary_and_recommendation(self) -> None:
        verdict = Verdict(
            summary="Both sides made compelling arguments.",
            recommendation="Pursue graduate school part-time.",
        )
        assert verdict.summary == "Both sides made compelling arguments."
        assert verdict.recommendation == "Pursue graduate school part-time."

    def test_created_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(timezone.utc)
        verdict = Verdict(summary="S.", recommendation="R.")
        after = datetime.now(timezone.utc)
        assert before <= verdict.created_at <= after

    def test_created_at_can_be_set_explicitly(self) -> None:
        fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
        verdict = Verdict(summary="S.", recommendation="R.", created_at=fixed)
        assert verdict.created_at == fixed

    def test_immutable_by_convention(self) -> None:
        verdict = Verdict(summary="S.", recommendation="R.")
        verdict.summary = "Updated."
        assert verdict.summary == "Updated."


# =================================================================
#  Debate  (Aggregate Root)
# =================================================================


class TestDebateCreation:
    """Debate is the aggregate root — tests for construction."""

    def test_create_with_required_fields(self) -> None:
        debate = Debate(id="deb-1", topic="Should I move abroad?")
        assert debate.id == "deb-1"
        assert debate.topic == "Should I move abroad?"
        assert debate.max_rounds == 3
        assert debate.status == DebateStatus.PENDING
        assert debate.rounds == []
        assert debate.verdict is None
        assert debate.updated_at is None
        assert debate.awaiting_input is False

    def test_create_with_custom_max_rounds(self) -> None:
        debate = Debate(id="deb-1", topic="Test", max_rounds=5)
        assert debate.max_rounds == 5

    def test_created_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(timezone.utc)
        debate = Debate(id="deb-2", topic="Test topic.")
        after = datetime.now(timezone.utc)
        assert before <= debate.created_at <= after

    def test_status_defaults_to_pending(self) -> None:
        debate = Debate(id="deb-3", topic="Should I change jobs?")
        assert debate.status == DebateStatus.PENDING

    def test_rounds_defaults_to_empty_list(self) -> None:
        debate = Debate(id="deb-4", topic="Test.")
        assert debate.rounds == []
        assert len(debate.rounds) == 0

    def test_verdict_defaults_to_none(self) -> None:
        debate = Debate(id="deb-5", topic="Test.")
        assert debate.verdict is None

    def test_awaiting_input_defaults_to_false(self) -> None:
        debate = Debate(id="deb-6", topic="Test.")
        assert debate.awaiting_input is False


class TestDebateAddRound:
    """Adding rounds to a debate."""

    def test_add_first_round(self) -> None:
        debate = Debate(id="deb-10", topic="Test.")
        round_ = Round(round_number=1)
        debate.add_round(round_)
        assert len(debate.rounds) == 1
        assert debate.rounds[0].round_number == 1
        assert debate.updated_at is not None

    def test_add_multiple_rounds_in_order(self) -> None:
        debate = Debate(id="deb-11", topic="Test.")
        for num in range(1, 4):
            debate.add_round(Round(round_number=num))
        assert len(debate.rounds) == 3
        assert [r.round_number for r in debate.rounds] == [1, 2, 3]

    def test_add_round_sets_updated_at(self) -> None:
        debate = Debate(id="deb-12", topic="Test.")
        before = datetime.now(timezone.utc)
        debate.add_round(Round(round_number=1))
        after = datetime.now(timezone.utc)
        assert debate.updated_at is not None
        assert before <= debate.updated_at <= after

    def test_add_round_does_not_affect_verdict(self) -> None:
        debate = Debate(id="deb-13", topic="Test.")
        debate.add_round(Round(round_number=1))
        assert debate.verdict is None
        assert debate.status == DebateStatus.PENDING

    def test_rounds_are_stored_in_insertion_order(self) -> None:
        debate = Debate(id="deb-14", topic="Test.")
        rounds = [Round(round_number=i) for i in (2, 1, 3)]
        for r in rounds:
            debate.add_round(r)
        assert debate.rounds[0].round_number == 2
        assert debate.rounds[1].round_number == 1
        assert debate.rounds[2].round_number == 3


class TestDebateAdvanceStatus:
    """Advancing the debate lifecycle status."""

    def test_advance_to_in_progress(self) -> None:
        debate = Debate(id="deb-20", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        assert debate.status == DebateStatus.IN_PROGRESS
        assert debate.updated_at is not None

    def test_advance_to_completed(self) -> None:
        debate = Debate(id="deb-21", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        debate.advance_status(DebateStatus.COMPLETED)
        assert debate.status == DebateStatus.COMPLETED

    def test_advance_to_error(self) -> None:
        debate = Debate(id="deb-22", topic="Test.")
        debate.advance_status(DebateStatus.ERROR)
        assert debate.status == DebateStatus.ERROR

    def test_status_transition_updates_timestamp(self) -> None:
        debate = Debate(id="deb-23", topic="Test.")
        before = datetime.now(timezone.utc)
        debate.advance_status(DebateStatus.IN_PROGRESS)
        after = datetime.now(timezone.utc)
        assert before <= debate.updated_at <= after  # type: ignore[operator]
        assert debate.updated_at >= debate.created_at


class TestDebateSetVerdict:
    """Setting the judge's verdict on a debate."""

    def test_set_verdict_marks_debate_completed(self) -> None:
        debate = Debate(id="deb-30", topic="Test.")
        verdict = Verdict(summary="S.", recommendation="R.")
        debate.set_verdict(verdict)
        assert debate.verdict is verdict
        assert debate.status == DebateStatus.COMPLETED

    def test_set_verdict_updates_timestamp(self) -> None:
        debate = Debate(id="deb-31", topic="Test.")
        before = datetime.now(timezone.utc)
        debate.set_verdict(Verdict(summary="S.", recommendation="R."))
        after = datetime.now(timezone.utc)
        assert before <= debate.updated_at <= after  # type: ignore[operator]

    def test_set_verdict_after_rounds(self) -> None:
        debate = Debate(id="deb-32", topic="Test.")
        debate.add_round(Round(round_number=1))
        debate.add_round(Round(round_number=2))
        debate.add_round(Round(round_number=3))
        verdict = Verdict(summary="S.", recommendation="R.")
        debate.set_verdict(verdict)
        assert len(debate.rounds) == 3
        assert debate.verdict is verdict
        assert debate.status == DebateStatus.COMPLETED

    def test_multiple_set_verdict_overwrites(self) -> None:
        debate = Debate(id="deb-33", topic="Test.")
        v1 = Verdict(summary="S1.", recommendation="R1.")
        v2 = Verdict(summary="S2.", recommendation="R2.")
        debate.set_verdict(v1)
        debate.set_verdict(v2)
        assert debate.verdict is v2


class TestDebateLatestRound:
    """Query: latest_round()"""

    def test_latest_round_with_no_rounds(self) -> None:
        debate = Debate(id="deb-40", topic="Test.")
        assert debate.latest_round() is None

    def test_latest_round_with_one_round(self) -> None:
        debate = Debate(id="deb-41", topic="Test.")
        round_ = Round(round_number=1)
        debate.add_round(round_)
        assert debate.latest_round() is round_

    def test_latest_round_returns_most_recent(self) -> None:
        debate = Debate(id="deb-42", topic="Test.")
        for num in range(1, 4):
            debate.add_round(Round(round_number=num))
        assert debate.latest_round() is not None
        assert debate.latest_round().round_number == 3  # type: ignore[union-attr]

    def test_latest_round_does_not_modify_rounds(self) -> None:
        debate = Debate(id="deb-43", topic="Test.")
        debate.add_round(Round(round_number=1))
        before = list(debate.rounds)
        _ = debate.latest_round()
        assert list(debate.rounds) == before


class TestDebateIsCompleted:
    """Query: is_completed()"""

    def test_pending_is_not_completed(self) -> None:
        debate = Debate(id="deb-50", topic="Test.")
        assert debate.is_completed() is False

    def test_in_progress_is_not_completed(self) -> None:
        debate = Debate(id="deb-51", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        assert debate.is_completed() is False

    def test_completed_is_completed(self) -> None:
        debate = Debate(id="deb-52", topic="Test.")
        debate.advance_status(DebateStatus.COMPLETED)
        assert debate.is_completed() is True

    def test_error_is_completed(self) -> None:
        debate = Debate(id="deb-53", topic="Test.")
        debate.advance_status(DebateStatus.ERROR)
        assert debate.is_completed() is True

    def test_set_verdict_makes_debate_completed(self) -> None:
        debate = Debate(id="deb-54", topic="Test.")
        debate.set_verdict(Verdict(summary="S.", recommendation="R."))
        assert debate.is_completed() is True


# =================================================================
#  Integration: end-to-end debate lifecycle
# =================================================================


class TestDebateLifecycle:
    """Simulate a full structured debate end-to-end."""

    def test_full_debate_lifecycle(self) -> None:
        debate = Debate(id="lifecycle-1", topic="Should I learn Rust?")

        # Initial state
        assert debate.status == DebateStatus.PENDING
        assert debate.rounds == []
        assert debate.verdict is None

        # Start
        debate.advance_status(DebateStatus.IN_PROGRESS)

        # Round 1 - structured
        r1_pro = Argument(role=AgentRole.PRO, content="Rust is memory-safe.")
        r1_con = Argument(
            role=AgentRole.CON, content="Rust has a steep learning curve."
        )
        r1_pro_rebuttal = Argument(
            role=AgentRole.PRO, content="The learning curve is worth it."
        )
        r1_con_rebuttal = Argument(
            role=AgentRole.CON, content="Time is better spent elsewhere."
        )
        r1_cross = [
            CrossExaminationQA(
                question_role=AgentRole.PRO,
                question="Is the learning curve really prohibitive?",
                answer_role=AgentRole.CON,
                answer="For most teams, yes.",
            ),
            CrossExaminationQA(
                question_role=AgentRole.CON,
                question="Can you guarantee performance benefits?",
                answer_role=AgentRole.PRO,
                answer="The data is clear.",
            ),
        ]
        r1 = Round(
            round_number=1,
            round_focus="Establish core arguments",
            moderator_intro="Let's begin with the basics.",
            pro_opening=r1_pro,
            con_opening=r1_con,
            cross_examination=r1_cross,
            pro_rebuttal=r1_pro_rebuttal,
            con_rebuttal=r1_con_rebuttal,
            moderator_summary="Strong opening from both sides.",
            moderator_steer="Address performance next.",
        )
        debate.add_round(r1)
        assert debate.latest_round() is r1
        assert debate.latest_round().round_focus == "Establish core arguments"  # type: ignore[union-attr]
        assert len(debate.latest_round().cross_examination) == 2  # type: ignore[union-attr]

        # Round 2
        r2_pro = Argument(role=AgentRole.PRO, content="Zero-cost abstractions.")
        r2_con = Argument(role=AgentRole.CON, content="Long compile times.")
        r2 = Round(
            round_number=2,
            round_focus="Challenge assumptions",
            moderator_intro="Let's probe deeper.",
            pro_opening=r2_pro,
            con_opening=r2_con,
        )
        debate.add_round(r2)

        # Round 3
        r3_pro = Argument(
            role=AgentRole.PRO, content="Growing ecosystem, WASM support."
        )
        r3_con = Argument(
            role=AgentRole.CON, content="Better alternatives for most projects."
        )
        r3 = Round(
            round_number=3,
            round_focus="Discuss practical implications",
            moderator_intro="Let's look at real-world impact.",
            pro_opening=r3_pro,
            con_opening=r3_con,
        )
        debate.add_round(r3)

        # Assert 3 rounds present
        assert len(debate.rounds) == 3
        assert [r.round_number for r in debate.rounds] == [1, 2, 3]

        # Verify round 1 structured data
        assert debate.rounds[0].round_focus == "Establish core arguments"
        assert debate.rounds[0].moderator_intro == "Let's begin with the basics."
        assert debate.rounds[0].moderator_summary == "Strong opening from both sides."
        assert len(debate.rounds[0].cross_examination) == 2
        assert debate.rounds[0].cross_examination[0].question_role == AgentRole.PRO
        assert debate.rounds[0].pro_rebuttal is not None
        assert debate.rounds[0].con_rebuttal is not None

        # Set verdict
        verdict = Verdict(
            summary="Both sides made strong cases.",
            recommendation="Learn Rust for systems work, skip for web-only.",
        )
        debate.set_verdict(verdict)

        # Final assertions
        assert debate.status == DebateStatus.COMPLETED
        assert debate.is_completed() is True
        assert debate.verdict is verdict
        assert (
            debate.verdict.recommendation
            == "Learn Rust for systems work, skip for web-only."
        )

    def test_debate_with_error_status(self) -> None:
        debate = Debate(id="error-1", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        debate.advance_status(DebateStatus.ERROR)
        assert debate.is_completed() is True
        assert debate.status == DebateStatus.ERROR
        assert debate.rounds == []
        assert debate.verdict is None

    def test_debate_with_partial_rounds_and_failure(self) -> None:
        debate = Debate(id="partial-1", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        debate.add_round(Round(round_number=1))
        debate.advance_status(DebateStatus.ERROR)
        assert debate.is_completed() is True
        assert len(debate.rounds) == 1


# =================================================================
#  Edge cases
# =================================================================


class TestDebateEdgeCases:
    """Edge-case behaviour for the domain models."""

    def test_topic_with_special_characters(self) -> None:
        debate = Debate(id="edge-1", topic="Should I buy a house in 2026? (Yes/No)")
        assert debate.topic == "Should I buy a house in 2026? (Yes/No)"

    def test_very_long_topic(self) -> None:
        long_topic = "Should I " + "very " * 50 + "long topic?"
        debate = Debate(id="edge-2", topic=long_topic)
        assert len(debate.topic) > 100

    def test_empty_round_content(self) -> None:
        """Content can be an empty string — validation is a service-layer concern."""
        arg = Argument(role=AgentRole.PRO, content="")
        round_ = Round(round_number=1, pro_opening=arg)
        assert round_.pro_opening is not None
        assert round_.pro_opening.content == ""

    def test_debate_uuid_formats(self) -> None:
        for id_ in ("abc-123", "uuid-like-value", "simple"):
            debate = Debate(id=id_, topic="Test.")
            assert debate.id == id_

    def test_round_without_arguments(self) -> None:
        """A round can exist without any arguments (before agents have spoken)."""
        round_ = Round(round_number=1)
        assert round_.pro_opening is None
        assert round_.con_opening is None
        assert round_.moderator_intro is None
        assert round_.moderator_summary is None
        assert round_.moderator_steer is None
        assert round_.cross_examination == []

    def test_created_at_timezone_is_utc(self) -> None:
        debate = Debate(id="tz-1", topic="Test.")
        assert debate.created_at.tzinfo is not None
        assert debate.created_at.tzinfo.utcoffset(
            debate.created_at
        ) == timezone.utc.utcoffset(debate.created_at)  # type: ignore[union-attr]

    def test_updated_at_is_set_on_round_add(self) -> None:
        debate = Debate(id="touch-1", topic="Test.")
        debate.add_round(Round(round_number=1))
        assert debate.updated_at is not None
        assert debate.updated_at >= debate.created_at

    def test_updated_at_is_set_on_status_advance(self) -> None:
        debate = Debate(id="touch-2", topic="Test.")
        debate.advance_status(DebateStatus.IN_PROGRESS)
        assert debate.updated_at is not None

    def test_updated_at_is_set_on_verdict(self) -> None:
        debate = Debate(id="touch-3", topic="Test.")
        debate.set_verdict(Verdict(summary="S.", recommendation="R."))
        assert debate.updated_at is not None

    def test_latest_round_on_empty_debate(self) -> None:
        debate = Debate(id="empty-1", topic="Test.")
        assert debate.latest_round() is None

    def test_is_completed_on_fresh_debate(self) -> None:
        debate = Debate(id="fresh-1", topic="Test.")
        assert debate.is_completed() is False
