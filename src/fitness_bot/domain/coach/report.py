from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import CoachReportStatus
from fitness_bot.domain.errors import DomainError


class CoachReport(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    reporter_user_id: UUID
    coach_user_id: UUID
    body: str
    status: CoachReportStatus = CoachReportStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    @classmethod
    def create(cls, *, reporter_user_id: UUID, coach_user_id: UUID, body: str) -> CoachReport:
        if reporter_user_id == coach_user_id:
            raise DomainError("cannot report yourself")
        text = body.strip()
        if not text:
            raise DomainError("report body is required")
        if len(text) > 1000:
            raise DomainError("report body must be ≤1000 characters")
        return cls(reporter_user_id=reporter_user_id, coach_user_id=coach_user_id, body=text)

    def resolve(self, *, now: datetime | None = None) -> None:
        if self.status == CoachReportStatus.RESOLVED:
            return
        self.status = CoachReportStatus.RESOLVED
        self.resolved_at = now or datetime.now(UTC)
