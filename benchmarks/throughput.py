"""
Plays real rooms through the gateway and measures the whole path of an action:
browser message, gateway, rules, Redis, event, delivery to every player.

  python throughput.py --rooms 200 --seconds 20 --ws ws://a/ws,ws://b/ws

Players of a room are spread over the listed gateways, so a working run with
two of them also proves that events cross between gateways.
"""
import argparse
import asyncio
import json
import multiprocessing
import time
import urllib.request

import websockets

ACTION_INTERVAL = 0.2  # Stays below the gateway's limit of 10 messages per second
RETRY_AFTER = 5  # An overloaded backend may refuse an action, or its answer may come late


def post(url, body):
    request = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json"})
    return json.load(urllib.request.urlopen(request))


class Seat:
    def __init__(self, socket):
        self.socket = socket
        self.state = None
        self.refused = 0

    async def read(self):
        async for raw in self.socket:
            message = json.loads(raw)
            if message["type"] == "state":
                if self.state is None or message["public"]["version"] >= self.state["public"]["version"]:
                    self.state = message
            elif message["type"] == "error":
                self.refused += 1

    def version(self):
        return self.state["public"]["version"] if self.state else -1

    async def act(self, action, payload=None):
        await self.socket.send(json.dumps({"type": "action", "request_id": 1, "action": action, "payload": payload or {}}))


async def open_room(api, urls):
    host = post(f"{api}/api/rooms", {"name": "A"})
    guest = post(f"{api}/api/rooms/{host['room_id']}/join", {"name": "B"})
    seats = []
    for index, session in enumerate((host, guest)):
        socket = await websockets.connect(urls[index % len(urls)], max_size=None)
        await socket.send(json.dumps({"type": "hello", "room_id": host["room_id"], "token": session["token"]}))
        seats.append(Seat(socket))
    return seats


def next_move(seats):
    """Returns the seat that has to act and its action, from what the server calls legal."""
    public = seats[0].state["public"]
    game = public["game"]
    for seat in seats:
        legal = seat.state["private"]["legal"]
        if legal["must_discard"]:
            cards, left = {}, legal["must_discard"]
            for resource, amount in seat.state["private"]["resources"].items():
                cards[resource] = min(amount, left)
                left -= cards[resource]
            return seat, "discard", {"cards": cards}

    seat = seats[game["current_seat"]]
    legal = seat.state["private"]["legal"]
    phase = game["turn_phase"]
    if phase == "setup":
        if legal["settlements"]:
            return seat, "build_settlement", legal["settlements"][0]
        return seat, "build_road", legal["roads"][0]
    if phase == "roll_dice":
        return seat, "roll_dice", None
    if phase == "move_robber":
        return seat, "move_robber", {"hex": legal["robber_hexes"][0]}
    if phase == "steal":
        return seat, "steal", {"victim_seat": legal["steal_targets"][0]}
    return seat, "end_turn", None


async def wait_for_version(seats, version):
    """True once every seat has seen a state newer than `version`."""
    deadline = time.monotonic() + RETRY_AFTER
    while any(seat.version() <= version for seat in seats):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.002)
    return True


async def play_room(seats, stop_at, latencies):
    readers = [asyncio.create_task(seat.read()) for seat in seats]
    try:
        while any(seat.state is None for seat in seats):
            if time.monotonic() > stop_at:
                return 0
            await asyncio.sleep(0.01)
        while seats[0].state["public"]["game"] is None or seats[1].state["public"]["game"] is None:
            if seats[0].state["public"]["game"] is None:
                await seats[0].act("start_game")
            await wait_for_version(seats, max(seat.version() for seat in seats))
            if time.monotonic() > stop_at:
                return 0

        while time.monotonic() < stop_at:
            version = max(seat.version() for seat in seats)
            seat, action, payload = next_move(seats)
            started = time.monotonic()
            await seat.act(action, payload)
            if await wait_for_version(seats, version):
                latencies.append(time.monotonic() - started)
            await asyncio.sleep(max(ACTION_INTERVAL - (time.monotonic() - started), 0))
    finally:
        for reader in readers:
            reader.cancel()
        for seat in seats:
            await seat.socket.close()
    return sum(seat.refused for seat in seats)


async def client(api, urls, rooms, seconds):
    opened = await asyncio.gather(*(open_room(api, urls) for _ in range(rooms)))
    latencies = []
    stop_at = time.monotonic() + seconds + 3
    results = await asyncio.gather(*(play_room(seats, stop_at, latencies) for seats in opened), return_exceptions=True)
    return latencies, sum(r for r in results if isinstance(r, int)), sum(isinstance(r, Exception) for r in results)


def run_client(args):
    return asyncio.run(client(*args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--ws", default="ws://localhost:8180/ws")
    parser.add_argument("--rooms", type=int, default=200)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--clients", type=int, default=4)
    options = parser.parse_args()

    urls = options.ws.split(",")
    jobs = [(options.api, urls, options.rooms // options.clients, options.seconds)] * options.clients
    with multiprocessing.Pool(options.clients) as pool:
        results = pool.map(run_client, jobs)

    latencies = sorted(value * 1000 for result in results for value in result[0])
    refused = sum(result[1] for result in results)
    failed = sum(result[2] for result in results)
    count = len(latencies)
    print(
        f"rooms={options.rooms} offered={options.rooms / ACTION_INTERVAL:.0f}/s "
        f"achieved={count / (options.seconds + 3):.0f}/s p50={latencies[count // 2]:.1f}ms "
        f"p99={latencies[count * 99 // 100]:.1f}ms actions={count} refused={refused} failed_rooms={failed}"
    )


if __name__ == "__main__":
    main()
