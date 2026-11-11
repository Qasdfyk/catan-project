"""
Rooms: the lobby, seats and their session tokens, and the single path through
which a game state changes (load, validate, save, publish) under a room lock.
"""
import asyncio
import logging
import random
import secrets
import time
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings as config
from app.models.game import GameState
from app.models.settings import GameSettings
from app.schemas.game_schemas import BOT_LEVELS, DEFAULT_BOT_LEVEL, RoomSession, SettingsUpdate
from app.services.actions import apply_action
from app.services.game_record import close_record, new_record
from app.services.record_store import RecordStore
from app.services.redis_service import RedisService
from app.services.serializer import GameSerializer
from app.services.views import private_view, public_view

MAX_SEATS = 4
MIN_SEATS_TO_START = 2
BOT_NAMES = ("Ada", "Boole", "Turing", "Lovelace")
# The turn timer stops after this many rounds of timed-out turns with nobody
# connected, so an abandoned game stops saving itself and Redis lets it expire
IDLE_ROUNDS_BEFORE_PAUSE = 2

log = logging.getLogger(__name__)


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
    def __init__(self, redis: RedisService, records: Optional[RecordStore] = None):
        self.redis = redis
        self.records = records or RecordStore(config.RECORDS_DIR)
        # Replaced in tests to move time forward
        self.clock = time.time
        # Picks who plays first among n seats; replaced in tests to fix the order
        self.first_seat = random.randrange

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
        """Asked by the gateway for every connection, so a player who comes back restarts a paused timer."""
        room = await self._load_room(room_id)
        seat = self._seat_by_token(room, token)
        if self._timer_paused(room):
            room = await self._resume_timer(room_id)
        game = await self._load_game(room)
        return {"seat": seat, "public": public_view(room, game), "private": private_view(game, seat)}

    async def perform_action(self, room_id: str, token: str, action_type: str, payload: Dict[str, Any]):
        async with self.redis.room_lock(room_id):
            room = await self._load_room(room_id)
            # The token is checked on every action, so a replaced session loses access at once
            seat = self._seat_by_token(room, token)
            game = await self._load_game(room)
            # Somebody is here, so a paused timer starts again with this commit
            room.pop("idle_timeouts", None)

            if action_type == "start_game":
                game = self._start_game(room, seat, self.first_seat)
                await self.redis.start_record(room_id, self._new_record(room, game))
                # Saved before the bots connect, which is why _commit comes first
                await self._commit(room, game)
                await self._summon_bots(room)
                return
            elif action_type == "add_bot":
                self._add_bot(room, seat, payload)
            elif action_type == "remove_bot":
                self._remove_bot(room, seat, payload.get("seat"))
            elif action_type == "set_bot_level":
                self._set_bot_level(room, seat, payload)
            elif action_type == "update_settings":
                self._update_settings(room, seat, payload)
            elif action_type == "replace_with_bot":
                await self._replace_with_bot(room, game, seat, payload.get("seat"))
                return
            elif action_type == "rematch":
                if await self._rematch(room, seat):
                    await self._commit(room, game)
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

    async def get_record(self, room_id: str) -> Dict[str, Any]:
        """The record of a finished game. It outlives the room, which Redis drops after a day."""
        try:
            record = await asyncio.to_thread(self.records.load, room_id)
        except ValueError:
            raise RoomNotFound() from None
        if record is not None:
            return record
        room = await self._load_room(room_id)
        if room["status"] != "finished":
            raise RoomConflict("The game is not over yet.")

        # The save at the end of the game failed. Nothing else changes a finished
        # room unless the host starts a rematch, so the download tries again, and
        # hands out the record from Redis even if the disk still refuses it.
        async with self.redis.room_lock(room_id):
            room = await self._load_room(room_id)
            if room.get("record_saved"):
                # Saved by a request that held the lock before this one
                record = await asyncio.to_thread(self.records.load, room_id)
            else:
                record = await self._save_record(room, await self._load_game(room))
                await self._store(room)
        if record is None:
            raise RoomNotFound()
        return record

    async def join_rematch(self, room_id: str, token: str) -> RoomSession:
        """Trades a session of a finished game for the same seat in its rematch."""
        room = await self._load_room(room_id)
        seat = self._seat_by_token(room, token)
        rematch_id = room.get("rematch_room_id")
        if not rematch_id:
            raise RoomConflict("There is no rematch yet.")

        entry = (await self._load_room(rematch_id))["seats"][seat]
        if entry.get("replaced"):
            # A player who came back to the finished game after leaving it takes the seat from the bot
            return await self.join_room(rematch_id, entry["name"])
        return RoomSession(room_id=rematch_id, token=room["seats"][seat]["rematch_token"], seat=seat)

    async def time_out(self, room_id: str) -> bool:
        """
        Finishes the turn of whoever let the time run out. Called by the bot
        service once a second for each due room, so an early, late or repeated
        call must do no harm. Returns whether a turn was finished.

        Turns that time out while no seat is connected are counted; after
        IDLE_ROUNDS_BEFORE_PAUSE rounds of them the timer stops (see
        _timer_paused). Without that, a game everyone left would play itself
        forever, since finishing a turn never builds and nobody can win, and
        every save would push back the expiry of its keys.
        """
        async with self.redis.room_lock(room_id):
            room = await self.redis.get_room(room_id)
            if room is None or room.get("turn_deadline") is None or room["status"] != "playing":
                await self.redis.clear_turn_deadline(room_id)
                return False
            if self.clock() < room["turn_deadline"]:
                return False

            game = await self._load_game(room)
            if await self.redis.online_seats(room_id, len(room["seats"])):
                room.pop("idle_timeouts", None)
            else:
                room["idle_timeouts"] = room.get("idle_timeouts", 0) + 1
            game.auto_finish_turn()
            if game.is_game_over:
                room["status"] = "finished"
            await self._commit(room, game)
            if self._timer_paused(room):
                log.info("Paused the turn timer of room %s: nobody connected for %d turns.",
                         room_id, room["idle_timeouts"])
            return True

    @staticmethod
    def _timer_paused(room: Dict[str, Any]) -> bool:
        idle_limit = IDLE_ROUNDS_BEFORE_PAUSE * len(room["seats"])
        return room["status"] == "playing" and room.get("idle_timeouts", 0) >= idle_limit

    async def _resume_timer(self, room_id: str) -> Dict[str, Any]:
        """Gives the turn on hold its full time again. Returns the room as saved."""
        async with self.redis.room_lock(room_id):
            room = await self._load_room(room_id)
            # Another connection may have resumed it while this one waited for the lock
            if self._timer_paused(room):
                room.pop("idle_timeouts")
                await self._commit(room, await self._load_game(room))
                log.info("Resumed the turn timer of room %s.", room_id)
            return room

    @staticmethod
    def _verify_lobby_host(room: Dict[str, Any], seat: int):
        if seat != room["host_seat"]:
            raise RoomError("Only the host can change the room.")
        if room["status"] != "lobby":
            raise RoomError("The game has already started.")

    @staticmethod
    def _bot_level(payload: Dict[str, Any]) -> str:
        level = payload.get("level", DEFAULT_BOT_LEVEL)
        if level not in BOT_LEVELS:
            raise RoomError("Choose easy, medium or hard.")
        return level

    @staticmethod
    def _bot_seat(room: Dict[str, Any], target: Any) -> Dict[str, Any]:
        seats = room["seats"]
        if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target < len(seats) or not seats[target].get("bot"):
            raise RoomError("That seat has no bot.")
        return seats[target]

    @classmethod
    def _add_bot(cls, room: Dict[str, Any], seat: int, payload: Dict[str, Any]):
        cls._verify_lobby_host(room, seat)
        level = cls._bot_level(payload)
        if len(room["seats"]) >= MAX_SEATS:
            raise RoomConflict("The room is full.")
        taken = {entry["name"].casefold() for entry in room["seats"]}
        name = next(n for n in BOT_NAMES if n.casefold() not in taken)
        room["seats"].append({"name": name, "token": secrets.token_urlsafe(24), "bot": True, "level": level})

    @classmethod
    def _remove_bot(cls, room: Dict[str, Any], seat: int, target: Any):
        cls._verify_lobby_host(room, seat)
        seats = room["seats"]
        cls._bot_seat(room, target)
        # Seats must not shift: the gateway routes private state by seat number
        if target != len(seats) - 1:
            raise RoomError("Only the last seat can be freed.")
        seats.pop()

    @classmethod
    def _set_bot_level(cls, room: Dict[str, Any], seat: int, payload: Dict[str, Any]):
        cls._verify_lobby_host(room, seat)
        entry = cls._bot_seat(room, payload.get("seat"))
        entry["level"] = cls._bot_level(payload)

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

        seats[target].update(token=secrets.token_urlsafe(24), bot=True, replaced=True, level=DEFAULT_BOT_LEVEL)
        await self._commit(room, game)
        await self.redis.summon_bot(room["room_id"], seats[target]["token"], DEFAULT_BOT_LEVEL)

    async def _rematch(self, room: Dict[str, Any], seat: int) -> bool:
        """
        Opens a lobby with the same players, seats and settings. Returns False
        when it already exists, so a second click changes nothing.
        """
        if seat != room["host_seat"]:
            raise RoomError("Only the host can start a rematch.")
        if room["status"] != "finished":
            raise RoomError("The game is not over yet.")
        if room.get("rematch_room_id"):
            return False

        seats = []
        for entry in room["seats"]:
            new_entry = {"name": entry["name"], "token": secrets.token_urlsafe(24)}
            if entry.get("replaced"):
                # A bot keeps the seat until the player who left returns by name
                new_entry.update(bot=True, replaced=True, level=DEFAULT_BOT_LEVEL)
            elif entry.get("bot"):
                new_entry.update(bot=True, level=entry.get("level", DEFAULT_BOT_LEVEL))
            seats.append(new_entry)

        rematch = {
            "room_id": uuid.uuid4().hex[:8],
            "version": 1,
            "status": "lobby",
            "host_seat": room["host_seat"],
            "seats": seats,
            "settings": GameSettings.from_dict(room.get("settings")).to_dict(),
        }
        await self.redis.save_room(rematch["room_id"], rematch)

        room["rematch_room_id"] = rematch["room_id"]
        for entry, new_entry in zip(room["seats"], seats, strict=True):
            entry["rematch_token"] = new_entry["token"]
        return True

    async def _summon_bots(self, room: Dict[str, Any]):
        for entry in room["seats"]:
            if entry.get("bot"):
                await self.redis.summon_bot(room["room_id"], entry["token"], entry.get("level", DEFAULT_BOT_LEVEL))

    @staticmethod
    def _start_game(room: Dict[str, Any], seat: int, first_seat) -> GameState:
        if seat != room["host_seat"]:
            raise RoomError("Only the host can start the game.")
        if room["status"] != "lobby":
            raise RoomError("The game has already started.")
        if len(room["seats"]) < MIN_SEATS_TO_START:
            raise RoomError(f"At least {MIN_SEATS_TO_START} players are needed.")

        settings = GameSettings.from_dict(room.get("settings"))
        # Seats keep their numbers (the gateway routes by them), so the order is
        # randomised by who starts, not by shuffling the seats
        names = [entry["name"] for entry in room["seats"]]
        game = GameState.create_new_game(names, settings, first_seat=first_seat(len(names)))
        room["status"] = "playing"
        return game

    async def _commit(self, room: Dict[str, Any], game: Optional[GameState]):
        room["version"] += 1
        await self._update_turn_deadline(room, game)
        if game is not None:
            await self.redis.save_game_state(
                room["room_id"], GameSerializer.game_to_dict(game), events=game.take_events()
            )
            if game.is_game_over and not room.get("record_saved"):
                await self._save_record(room, game)
        await self._store(room)
        await self.redis.publish_event(self._event(room, game))

    @staticmethod
    def _new_record(room: Dict[str, Any], game: GameState) -> Dict[str, Any]:
        players = [
            {"kind": "bot", "bot_level": entry.get("level", DEFAULT_BOT_LEVEL)} if entry.get("bot") else {}
            for entry in room["seats"]
        ]
        return new_record(game, source="platform", players=players, game_id=room["room_id"])

    async def _save_record(self, room: Dict[str, Any], game: GameState) -> Optional[Dict[str, Any]]:
        """
        Moves the record of a finished game from Redis to disk and sets
        room["record_saved"]. A failure is logged and leaves the record in
        Redis, so a rematch or a download tries again; the game itself must end
        either way. Returns the closed record, saved or not, or None for a game
        that has none.
        """
        room_id = room["room_id"]
        room["record_saved"] = False
        record = await self.redis.load_record(room_id)
        if record is None:
            log.warning("Room %s finished without a record; it started before records existed.", room_id)
            return None
        close_record(record, game)
        try:
            await asyncio.to_thread(self.records.save, room_id, record)
        except OSError:
            log.exception("Could not save the record of room %s.", room_id)
            return record
        await self.redis.drop_record(room_id)
        room["record_saved"] = True
        return record

    async def _update_turn_deadline(self, room: Dict[str, Any], game: Optional[GameState]):
        """Every step of a turn (rolling, discarding, moving the robber...) gets the full time."""
        if (game is None or room["status"] != "playing" or game.is_game_over
                or not game.settings.turn_seconds or self._timer_paused(room)):
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
