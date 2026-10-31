"""
Rooms: the lobby, seats and their session tokens, and the single path through
which a game state changes (load, validate, save, publish) under a room lock.
"""
import secrets
import uuid
from typing import Any, Dict, Optional, Tuple

from app.models.game import GameState
from app.schemas.game_schemas import RoomSession
from app.services.actions import apply_action
from app.services.redis_service import RedisService
from app.services.serializer import GameSerializer
from app.services.views import private_view, public_view

MAX_SEATS = 4
MIN_SEATS_TO_START = 2


class RoomError(Exception):
    """An expected failure with a message for the user."""
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RoomNotFound(RoomError):
    status_code = 404

    def __init__(self):
        super().__init__("This room does not exist.")


class RoomConflict(RoomError):
    status_code = 409


class InvalidSession(RoomError):
    status_code = 401

    def __init__(self):
        super().__init__("Your session is no longer valid. Join the room again.")


class RoomService:
    def __init__(self, redis: RedisService):
        self.redis = redis

    async def create_room(self, host_name: str) -> RoomSession:
        room_id = uuid.uuid4().hex[:8]
        token = secrets.token_urlsafe(24)
        room = {
            "room_id": room_id,
            "version": 1,
            "status": "lobby",
            "host_seat": 0,
            "seats": [{"name": host_name, "token": token}],
        }
        await self.redis.save_room(room_id, room)
        return RoomSession(room_id=room_id, token=token, seat=0)

    async def join_room(self, room_id: str, name: str) -> RoomSession:
        """Takes a free seat, or returns to one by name if nobody is connected to it."""
        async with self.redis.room_lock(room_id):
            room = await self._load_room(room_id)
            token = secrets.token_urlsafe(24)

            seat = self._seat_by_name(room, name)
            if seat is not None:
                if seat in await self.redis.online_seats(room_id, len(room["seats"])):
                    raise RoomConflict("That name is taken by a connected player.")
                room["seats"][seat]["token"] = token
                await self._store(room)
                return RoomSession(room_id=room_id, token=token, seat=seat)

            if room["status"] != "lobby":
                raise RoomConflict("The game has already started.")
            if len(room["seats"]) >= MAX_SEATS:
                raise RoomConflict("The room is full.")

            room["seats"].append({"name": name, "token": token})
            seat = len(room["seats"]) - 1
            await self._commit(room, None)
            return RoomSession(room_id=room_id, token=token, seat=seat)

    async def get_summary(self, room_id: str) -> Dict[str, Any]:
        room = await self._load_room(room_id)
        online = await self.redis.online_seats(room_id, len(room["seats"]))
        return {
            "room_id": room_id,
            "status": room["status"],
            "players": [
                {"name": entry["name"], "online": seat in online}
                for seat, entry in enumerate(room["seats"])
            ],
        }

    async def get_session_state(self, room_id: str, token: str) -> Dict[str, Any]:
        room = await self._load_room(room_id)
        seat = self._seat_by_token(room, token)
        game = await self._load_game(room)
        return {"seat": seat, "public": public_view(room, game), "private": private_view(game, seat)}

    async def perform_action(self, room_id: str, token: str, action_type: str, payload: Dict[str, Any]):
        async with self.redis.room_lock(room_id):
            room = await self._load_room(room_id)
            # The token is checked on every action, so a replaced session loses access at once
            seat = self._seat_by_token(room, token)
            game = await self._load_game(room)

            if action_type == "start_game":
                game = self._start_game(room, seat)
            elif game is None:
                raise RoomError("The game has not started yet.")
            else:
                try:
                    apply_action(game, seat, action_type, payload)
                except ValueError as error:
                    raise RoomError(str(error)) from None
                if game.is_game_over:
                    room["status"] = "finished"

            await self._commit(room, game)

    @staticmethod
    def _start_game(room: Dict[str, Any], seat: int) -> GameState:
        if seat != room["host_seat"]:
            raise RoomError("Only the host can start the game.")
        if room["status"] != "lobby":
            raise RoomError("The game has already started.")
        if len(room["seats"]) < MIN_SEATS_TO_START:
            raise RoomError(f"At least {MIN_SEATS_TO_START} players are needed.")

        game = GameState.create_new_game([entry["name"] for entry in room["seats"]])
        room["status"] = "playing"
        return game

    async def _commit(self, room: Dict[str, Any], game: Optional[GameState]):
        room["version"] += 1
        if game is not None:
            await self.redis.save_game_state(room["room_id"], GameSerializer.game_to_dict(game))
        await self._store(room)
        await self.redis.publish_event(self._event(room, game))

    async def _store(self, room: Dict[str, Any]):
        await self.redis.save_room(room["room_id"], room)

    @staticmethod
    def _event(room: Dict[str, Any], game: Optional[GameState]) -> Dict[str, Any]:
        return {
            "room_id": room["room_id"],
            "public": public_view(room, game),
            "private": {
                str(seat): private_view(game, seat) for seat in range(len(room["seats"]))
            },
        }

    async def _load_room(self, room_id: str) -> Dict[str, Any]:
        room = await self.redis.get_room(room_id)
        if room is None:
            raise RoomNotFound()
        return room

    async def _load_game(self, room: Dict[str, Any]) -> Optional[GameState]:
        if room["status"] == "lobby":
            return None
        data = await self.redis.get_game_state(room["room_id"])
        if data is None:
            raise RoomNotFound()
        return GameSerializer.dict_to_game(data)

    @staticmethod
    def _seat_by_name(room: Dict[str, Any], name: str) -> Optional[int]:
        wanted = name.casefold()
        for seat, entry in enumerate(room["seats"]):
            if entry["name"].casefold() == wanted:
                return seat
        return None

    @staticmethod
    def _seat_by_token(room: Dict[str, Any], token: str) -> int:
        for seat, entry in enumerate(room["seats"]):
            if secrets.compare_digest(entry["token"], token):
                return seat
        raise InvalidSession()
