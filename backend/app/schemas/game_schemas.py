from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.models.settings import DISCARD_LIMIT, VICTORY_POINTS_TO_WIN


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


SETTING_ERRORS = {
    "victory_points": "Victory points must be a whole number from 6 to 15.",
    "discard_limit": "The discard limit must be a whole number from 5 to 12.",
    "desert": "The desert must be \"random\" or \"center\".",
    "friendly_robber": "The friendly robber must be on or off.",
    "turn_seconds": "The turn time must be 60, 90, 120 or 180 seconds, or none.",
}


class SettingsUpdate(BaseModel):
    """A partial change to the room settings: only the keys sent are applied."""
    model_config = ConfigDict(extra="forbid", strict=True)

    victory_points: int = Field(default=VICTORY_POINTS_TO_WIN, ge=6, le=15)
    discard_limit: int = Field(default=DISCARD_LIMIT, ge=5, le=12)
    desert: Literal["random", "center"] = "random"
    friendly_robber: bool = False
    turn_seconds: Optional[Literal[60, 90, 120, 180]] = None

    @classmethod
    def changes(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Returns the valid keys of `payload`, or raises ValueError with a message for the user."""
        try:
            update = cls.model_validate(payload)
        except ValidationError as error:
            first = error.errors()[0]
            name = str(first["loc"][0])
            if first["type"] == "extra_forbidden":
                raise ValueError(f"Unknown setting: {name}.") from None
            raise ValueError(SETTING_ERRORS[name]) from None
        return update.model_dump(exclude_unset=True)
