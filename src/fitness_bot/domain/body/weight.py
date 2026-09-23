from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import WeightSource
from fitness_bot.domain.errors import InvalidWeight


class WeightEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    kilograms: Decimal
    measured_at: datetime
    source: WeightSource

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        kilograms: Decimal | str | float,
        measured_at: datetime,
        source: WeightSource,
    ) -> WeightEntry:
        value = Decimal(str(kilograms))
        if value <= 0:
            raise InvalidWeight("kilograms must be positive")
        return cls(user_id=user_id, kilograms=value, measured_at=measured_at, source=source)

    def rerecord(
        self,
        *,
        kilograms: Decimal | str | float,
        measured_at: datetime,
        source: WeightSource,
    ) -> None:
        value = Decimal(str(kilograms))
        if value <= 0:
            raise InvalidWeight("kilograms must be positive")
        self.kilograms = value
        self.measured_at = measured_at
        self.source = source
