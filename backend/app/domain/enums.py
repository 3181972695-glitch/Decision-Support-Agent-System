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
