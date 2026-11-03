"""House rules a host picks in the lobby. The defaults are the standard rules."""
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional

VICTORY_POINTS_TO_WIN = 10
DISCARD_LIMIT = 7
# With the friendly robber, opponents with this many visible points or fewer are left alone
FRIENDLY_ROBBER_MAX_POINTS = 2

DESERT_RANDOM = "random"
DESERT_CENTER = "center"


@dataclass(frozen=True)
class GameSettings:
    victory_points: int = VICTORY_POINTS_TO_WIN
    # On a 7, players holding more cards than this discard half
    discard_limit: int = DISCARD_LIMIT
    desert: str = DESERT_RANDOM
    friendly_robber: bool = False
    # Shown to the players only: there is no turn timer yet
    turn_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'GameSettings':
        """Missing keys take the defaults, so rooms and games saved before settings existed still load."""
        known = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in (data or {}).items() if key in known})
