from __future__ import annotations


class DomainError(Exception):
    """Base domain invariant violation."""


class InvalidProfileValue(DomainError):
    """Profile field value does not satisfy domain rules."""


class ProfileIncomplete(DomainError):
    """Required profile data is missing."""


class InvalidMeasurement(DomainError):
    """Measurement value or site is invalid."""


class InvalidWeight(DomainError):
    """Weight value is invalid."""


class InvalidReminder(DomainError):
    """Weight reminder schedule is invalid."""


class InvalidWorkoutDocument(DomainError):
    """Workout document violates domain invariants."""


class UnresolvedExercises(DomainError):
    """Approve blocked while a slot has no catalog exercise_id."""


class EmptyProgramWeek(DomainError):
    """Approve blocked for a week with no days or no slots."""


class AgentUnavailable(DomainError):
    """Language model timed out, returned 5xx, or was unreachable; document must not change."""
