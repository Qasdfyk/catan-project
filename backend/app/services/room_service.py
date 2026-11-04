"""
Rooms: the lobby, seats and their session tokens, and the single path through
which a game state changes (load, validate, save, publish) under a room lock.
"""
import secrets
import time
import uuid
from typing import Any, Dict, Optional

from app.models.game import GameState
from app.models.settings import GameSettings
from app.schemas.game_schemas import RoomSession, SettingsUpdate
from app.services.actions import apply_action
from app.services.redis_service import RedisService
from app.services.serializer import GameSerializer
from app.services.views import private_view, public_view

MAX_SEATS = 4
MIN_SEATS_TO_START = 2
BOT_NAMES = ("Ada", "Boole", "Turing", "Lovelace")


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
        # Replaced in tests to move time forward
        self.clock = time.time

    async def create_room(self, host_name: str) -> RoomSession:
        room_id = uuid.uuid4().hex[:8]
        token = secrets.token_urlsafe(24)
        room = {
            "room_id": room_id,
            "version": 1,
            "status": "lobby",
            "host_seat": 0,
            "seats": [{"name": host_name, "token": token}],
            "settings": GameSettings().to_dict(),
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
                entry = room["seats"][seat]
                if entry.get("replaced"):
                    # The new token also ends the bot, on its next move at the latest
                    entry.update(token=token, bot=False, replaced=False)
                    await self._commit(room, await self._load_game(room))
                    return RoomSession(room_id=room_id, token=token, seat=seat)
                if entry.get("bot"):
                    raise RoomConflict("That name belongs to a bot.")
                if seat in await self.redis.online_seats(room_id, len(room["seats"])):
                    raise RoomConflict("That name is taken by a connected player.")
                entry["token"] = token
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
                {"name": entry["name"], "online": seat in online and not entry.get("replaced")}
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
                # Saved before the bots connect, which is why _commit comes first
                await self._commit(room, game)
                await self._summon_bots(room)
                return
            elif action_type == "add_bot":
                self._add_bot(room, seat)
            elif action_type == "remove_bot":
                self._remove_bot(room, seat, payload.get("seat"))
            elif action_type == "update_settings":
                self._update_settings(room, seat, payload)
            elif action_type == "replace_with_bot":
                await self._replace_with_bot(room, game, seat, payload.get("seat"))
                return
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

    async def time_out(self, room_id: str) -> bool:
        """
        Finishes the turn of whoever let the time run out. Called by the bot
        service once a second for each due room, so an early, late or repeated
        call must do no harm. Returns whether a turn was finished.
        """
        async with self.redis.room_lock(room_id):
            room = await self.redis.get_room(room_id)
            if room is None or room.get("turn_deadline") is None or room["status"] != "playing":
                await self.redis.clear_turn_deadline(room_id)
                return False
            if self.clock() < room["turn_deadline"]:
                return False

            game = await self._load_game(room)
            game.auto_finish_turn()
            if game.is_game_over:
                room["status"] = "finished"
            await self._commit(room, game)
            return True

    @staticmethod
    def _verify_lobby_host(room: Dict[str, Any], seat: int):
        if seat != room["host_seat"]:
            raise RoomError("Only the host can change the room.")
        if room["status"] != "lobby":
            raise RoomError("The game has already started.")

    @classmethod
    def _add_bot(cls, room: Dict[str, Any], seat: int):
        cls._verify_lobby_host(room, seat)
        if len(room["seats"]) >= MAX_SEATS:
            raise RoomConflict("The room is full.")
        taken = {entry["name"].casefold() for entry in room["seats"]}
        name = next(n for n in BOT_NAMES if n.casefold() not in taken)
        room["seats"].append({"name": name, "token": secrets.token_urlsafe(24), "bot": True})

    @classmethod
    def _remove_bot(cls, room: Dict[str, Any], seat: int, target: Any):
        cls._verify_lobby_host(room, seat)
        seats = room["seats"]
        if not isinstance(target, int) or not 0 <= target < len(seats) or not seats[target].get("bot"):
            raise RoomError("That seat has no bot.")
        # Seats must not shift: the gateway routes private state by seat number
        if target != len(seats) - 1:
            raise RoomError("Only the last seat can be freed.")
        seats.pop()

    @classmethod
    def _update_settings(cls, room: Dict[str, Any], seat: int, payload: Dict[str, Any]):
        """Merges a partial change; the game takes a copy when it starts, so later changes are refused."""
        cls._verify_lobby_host(room, seat)
        try:
            changes = SettingsUpdate.changes(payload)
        except ValueError as error:
            raise RoomError(str(error)) from None
        # Rooms created before settings existed have none stored
        room["settings"] = {**GameSettings.from_dict(room.get("settings")).to_dict(), **changes}

    async def _replace_with_bot(self, room: Dict[str, Any], game: Optional[GameState], seat: int, target: Any):
        """Keeps a game going when a player left. They can return by name at any time."""
        if room["status"] != "playing":
            raise RoomError("The game is not running.")
        seats = room["seats"]
        if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target < len(seats) or target == seat:
            raise RoomError("Choose another player.")
        if seats[target].get("bot"):
            raise RoomError("A bot is already playing there.")
        if target in await self.redis.online_seats(room["room_id"], len(seats)):
            raise RoomError("That player is connected.")

        seats[target].update(token=secrets.token_urlsafe(24), bot=True, replaced=True)
        await self._commit(room, game)
        await self.redis.summon_bot(room["room_id"], seats[target]["token"])

    async def _summon_bots(self, room: Dict[str, Any]):
        for entry in room["seats"]:
            if entry.get("bot"):
                await self.redis.summon_bot(room["room_id"], entry["token"])

    @staticmethod
    def _start_game(room: Dict[str, Any], seat: int) -> GameState:
        if seat != room["host_seat"]:
            raise RoomError("Only the host can start the game.")
        if room["status"] != "lobby":
            raise RoomError("The game has already started.")
        if len(room["seats"]) < MIN_SEATS_TO_START:
            raise RoomError(f"At least {MIN_SEATS_TO_START} players are needed.")

        settings = GameSettings.from_dict(room.get("settings"))
        game = GameState.create_new_game([entry["name"] for entry in room["seats"]], settings)
        room["status"] = "playing"
        return game

    async def _commit(self, room: Dict[str, Any], game: Optional[GameState]):
        room["version"] += 1
        await self._update_turn_deadline(room, game)
        if game is not None:
            await self.redis.save_game_state(room["room_id"], GameSerializer.game_to_dict(game))
        await self._store(room)
        await self.redis.publish_event(self._event(room, game))

    async def _update_turn_deadline(self, room: Dict[str, Any], game: Optional[GameState]):
        """Every step of a turn (rolling, discarding, moving the robber...) gets the full time."""
        if game is None or room["status"] != "playing" or game.is_game_over or not game.settings.turn_seconds:
            room.update(turn_deadline=None, turn_key=None)
            await self.redis.clear_turn_deadline(room["room_id"])
            return

        key = f"{game.turn_number}:{game.turn_phase.value}"
        if room.get("turn_key") != key or room.get("turn_deadline") is None:
            room.update(turn_deadline=self.clock() + game.settings.turn_seconds, turn_key=key)
        # Set on every change, so the set heals if it lost a room
        await self.redis.set_turn_deadline(room["room_id"], room["turn_deadline"])

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
