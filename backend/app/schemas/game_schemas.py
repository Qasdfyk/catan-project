from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class PlayerNameRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not 1 <= len(value) <= 20:
            raise ValueError("Name must be between 1 and 20 characters.")
        return value


class RoomSession(BaseModel):
    room_id: str
    token: str
    seat: int


class SessionRequest(BaseModel):
    token: str


class ActionRequest(BaseModel):
    token: str
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
