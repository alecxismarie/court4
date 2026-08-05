from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    storage: Literal["ok", "unavailable"]


class TestDatabaseIdentityResponse(BaseModel):
    database_name: str
