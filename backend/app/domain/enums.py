"""Enumerations for the debate domain."""

from enum import Enum


class DebateStatus(str, Enum):
    """Possible states of a debate lifecycle."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"


class AgentRole(str, Enum):
    """Roles available in the debate system."""

    PRO = "pro"
    CON = "con"
    MODERATOR = "moderator"
    JUDGE = "judge"


class ResponseType(str, Enum):
    """Type of response an agent should produce.

    Used to differentiate between opening arguments, rebuttals,
    cross-examination questions, and answers within the same agent class.
    """

    OPENING = "opening"
    REBUTTAL = "rebuttal"
    CROSS_EXAMINE_ASK = "cross_examine_ask"
    CROSS_EXAMINE_ANSWER = "cross_examine_answer"
    USER_ANSWER = "user_answer"
    VERDICT = "verdict"
    MODERATOR_INTRO = "moderator_intro"
    MODERATOR_SUMMARY = "moderator_summary"
