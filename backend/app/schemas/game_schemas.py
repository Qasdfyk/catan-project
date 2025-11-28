from pydantic import BaseModel
from typing import List, Dict, Any

class GameCreateRequest(BaseModel):
    player_names: List[str]

class GameResponse(BaseModel):
    room_id: str
    status: str
    created_at: str
    players: List[Dict[str, Any]]