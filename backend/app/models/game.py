from typing import Any, List, Optional, Dict, Set
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum

from app.models.board import Board, ResourceType, PortType
from app.models.player import DevCard, Player, PlayerColor
from app.models.hex_lib import Edge, Vertex, Hex
from app.models.recording import cards_json, corner_json, hex_json, recorded
from app.models.settings import FRIENDLY_ROBBER_MAX_POINTS, GameSettings

class TurnPhase(str, Enum):
    SETUP = "setup"
    ROLL_DICE = "roll_dice"
    DISCARD = "discard"
    MOVE_ROBBER = "move_robber"
    STEAL = "steal"
    ROAD_BUILDING = "road_building"
    MAIN_PHASE = "main_phase"

class BuildingType(str, Enum):
    SETTLEMENT = "settlement"
    CITY = "city"

ROAD_COST = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
SETTLEMENT_COST = {
    ResourceType.WOOD: 1, ResourceType.BRICK: 1,
    ResourceType.WHEAT: 1, ResourceType.SHEEP: 1
}
CITY_COST = {ResourceType.ORE: 3, ResourceType.WHEAT: 2}
DEV_CARD_COST = {ResourceType.ORE: 1, ResourceType.WHEAT: 1, ResourceType.SHEEP: 1}

DEV_DECK = (
    [DevCard.KNIGHT] * 14 + [DevCard.VICTORY_POINT] * 5 +
    [DevCard.ROAD_BUILDING] * 2 + [DevCard.YEAR_OF_PLENTY] * 2 + [DevCard.MONOPOLY] * 2
)

MAX_ROADS = 15
MAX_SETTLEMENTS = 5
MAX_CITIES = 4

LONGEST_ROAD_MIN_LENGTH = 5
LONGEST_ROAD_POINTS = 2
LARGEST_ARMY_MIN_KNIGHTS = 3
LARGEST_ARMY_POINTS = 2
ROAD_BUILDING_ROADS = 2
BANK_SIZE = 19
LOG_SIZE = 40
# Two dice give totals from 2 to 12
DICE_TOTALS = range(2, 13)
FRIENDLY_ROBBER_ERROR = (
    f"The friendly robber leaves players with {FRIENDLY_ROBBER_MAX_POINTS} points or fewer alone."
)

TRADABLE_RESOURCES = [r for r in ResourceType if r != ResourceType.DESERT]

PHASE_ERRORS = {
    TurnPhase.SETUP: "Finish the setup phase first.",
    TurnPhase.ROLL_DICE: "You must roll the dice first.",
    TurnPhase.DISCARD: "Waiting for players to discard.",
    TurnPhase.MOVE_ROBBER: "You must move the robber first.",
    TurnPhase.STEAL: "You must choose a player to steal from.",
    TurnPhase.ROAD_BUILDING: "Place your free roads first.",
    TurnPhase.MAIN_PHASE: "You have already rolled the dice.",
}

@dataclass
class TradeOffer:
    """An open offer from the current player, seen by everyone."""
    proposer: PlayerColor
    give: Dict[ResourceType, int]
    get: Dict[ResourceType, int]
    accepted: List[PlayerColor] = field(default_factory=list)
    declined: List[PlayerColor] = field(default_factory=list)

@dataclass
class Building:
    owner: PlayerColor
    type: BuildingType

@dataclass
class GameState:
    """
    The root entity for the game logic.
    """
    board: Board
    players: List[Player] = field(default_factory=list)
    settings: GameSettings = field(default_factory=GameSettings)
    current_turn_index: int = 0
    # Counts the turns that have ended, setup turns included; a turn timer restarts when it changes
    turn_number: int = 0
    dice_roll: Optional[int] = None
    dice: List[int] = field(default_factory=list)
    # How often each total was rolled this game: index 0 counts the 2s, index 10 the 12s
    roll_counts: List[int] = field(default_factory=lambda: [0] * len(DICE_TOTALS))
    turn_phase: TurnPhase = TurnPhase.SETUP

    # --- SETUP PHASE STATE ---
    # Stores the sequence of player indices for the snake draft (e.g., [0, 1, 1, 0])
    setup_queue: List[int] = field(default_factory=list)
    # If true, the current player in setup must place a road. If false, they must place a settlement.
    setup_waiting_for_road: bool = False
    # The settlement just placed in setup: the road of this setup turn must touch it.
    setup_last_vertex: Optional[Vertex] = None

    # Robber position (initially should be on Desert)
    robber_hex: Optional[Hex] = None

    # Cards each player still has to give up after a 7
    pending_discards: Dict[PlayerColor, int] = field(default_factory=dict)

    # Where the turn continues after the robber or free roads (a card can be played before rolling)
    return_phase: TurnPhase = TurnPhase.MAIN_PHASE
    free_roads_left: int = 0

    trade_offer: Optional[TradeOffer] = None

    dev_deck: List[DevCard] = field(default_factory=list)
    dev_card_played: bool = False
    largest_army_holder: Optional[PlayerColor] = None

    longest_road_holder: Optional[PlayerColor] = None
    road_lengths: Dict[PlayerColor, int] = field(default_factory=dict)

    is_game_over: bool = False
    winner: Optional[Player] = None

    log: List[str] = field(default_factory=list)

    # State of the board
    roads: Dict[Edge, PlayerColor] = field(default_factory=dict)
    # Maps Vertex -> Building object
    settlements: Dict[Vertex, Building] = field(default_factory=dict)

    # --- Not saved with the state ---
    # Where dice and steals come from; a replay swaps in the recorded outcomes
    rng: Any = field(default=random, repr=False, compare=False)
    # Actions accepted since the caller last took them (see recording.py)
    events: List[Dict[str, Any]] = field(default_factory=list, repr=False, compare=False)
    _record_depth: int = field(default=0, repr=False, compare=False)
    _auto: bool = field(default=False, repr=False, compare=False)

    @staticmethod
    def create_new_game(
        player_names: List[str],
        settings: Optional[GameSettings] = None,
        board: Optional[Board] = None,
        dev_deck: Optional[List[DevCard]] = None,
    ) -> 'GameState':
        """A replay passes the recorded board and deck; a new game draws its own."""
        if len(player_names) < 2 or len(player_names) > 4:
            raise ValueError("Game requires 2 to 4 players.")

        settings = settings or GameSettings()
        board = board or Board.create_standard_game(desert=settings.desert)
        players = []
        colors = list(PlayerColor)

        for i, name in enumerate(player_names):
            # Generate UUIDs for players to allow reconnects/identification
            new_player = Player(name=name, color=colors[i], id=str(uuid.uuid4()))
            players.append(new_player)

        # Find Desert to place Robber initially
        desert_hex = next((t.hex_coords for t in board.tiles.values() if t.resource == ResourceType.DESERT), Hex(0,0,0))

        # Create Snake Draft Queue: [0, 1, 2, 2, 1, 0]
        indices = list(range(len(players)))
        setup_queue = indices + indices[::-1]

        if dev_deck is None:
            dev_deck = list(DEV_DECK)
            random.shuffle(dev_deck)

        return GameState(
            board=board,
            players=players,
            settings=settings,
            dev_deck=dev_deck,
            robber_hex=desert_hex,
            turn_phase=TurnPhase.SETUP,
            setup_queue=setup_queue,
            current_turn_index=setup_queue[0]
        )

    def take_events(self) -> List[Dict[str, Any]]:
        """Returns the actions recorded since the last call and forgets them."""
        events, self.events = self.events, []
        return events

    def seat_of(self, player: Player) -> int:
        return next(seat for seat, p in enumerate(self.players) if p.color == player.color)

    def get_current_player(self) -> Player:
        return self.players[self.current_turn_index]

    def get_player_by_color(self, color: PlayerColor) -> Player:
        return next(p for p in self.players if p.color == color)

    @recorded("end_turn")
    def end_turn(self, player: Player):
        """A player's request to finish their turn; only legal after rolling."""
        self._verify_turn(player)
        self.next_turn()
        if not self.is_game_over:
            self._log(f"{self.get_current_player().name}'s turn.")

    def next_turn(self):
        self._check_victory()
        if self.is_game_over:
            return

        self.turn_number += 1
        if self.turn_phase == TurnPhase.SETUP:
            # Remove the turn we just finished
            self.setup_queue.pop(0)
            self.setup_waiting_for_road = False
            self.setup_last_vertex = None

            if not self.setup_queue:
                # End of Setup
                self.turn_phase = TurnPhase.ROLL_DICE
                self.current_turn_index = 0
                self.dice_roll = None
            else:
                # Next setup turn
                self.current_turn_index = self.setup_queue[0]
        else:
            # Normal Game Loop
            self.trade_offer = None
            finished = self.get_current_player()
            finished.dev_cards.extend(finished.new_dev_cards)
            finished.new_dev_cards = []
            self.dev_card_played = False

            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
            self.dice_roll = None
            self.turn_phase = TurnPhase.ROLL_DICE
            # Points gained outside of one's turn (Longest Road) only win on one's own turn
            self._check_victory()

    def auto_finish_turn(self, rng=random):
        """
        Ends the turn for whoever is holding it up, doing only what the rules
        require: random placements in setup, random discards, a random robber
        hex and victim. Every move goes through the public methods, so all rule
        checks still apply.
        """
        self._verify_active()
        blockers = (
            [self.get_player_by_color(c) for c in self.pending_discards]
            if self.turn_phase == TurnPhase.DISCARD else [self.get_current_player()]
        )
        for player in blockers:
            self._log(f"{player.name} ran out of time.")

        turn = self.turn_number
        self._auto = True
        try:
            while not self.is_game_over and self.turn_number == turn:
                self._auto_step(rng)
        finally:
            self._auto = False

    def _auto_step(self, rng):
        player = self.get_current_player()
        phase = self.turn_phase

        if phase == TurnPhase.SETUP:
            if not self.setup_waiting_for_road:
                self.place_settlement(player, rng.choice(self.legal_settlements(player)))
            else:
                self.place_road(player, rng.choice(self.legal_roads(player)))
        elif phase == TurnPhase.ROLL_DICE:
            self.roll_dice(player)
        elif phase == TurnPhase.DISCARD:
            for color, required in list(self.pending_discards.items()):
                loser = self.get_player_by_color(color)
                cards: Dict[ResourceType, int] = {}
                pool = [r for r, n in loser.resources.items() for _ in range(n)]
                for resource in rng.sample(pool, required):
                    cards[resource] = cards.get(resource, 0) + 1
                self.discard(loser, cards)
        elif phase == TurnPhase.MOVE_ROBBER:
            self.move_robber(player, rng.choice(self.legal_robber_hexes(player)))
        elif phase == TurnPhase.STEAL:
            victims = self.steal_victims(player)
            if victims:
                self.steal_resource(player, rng.choice(victims))
            else:
                # Only a hand changed outside the rules leaves nobody to steal from
                self.turn_phase = self.return_phase
        elif phase == TurnPhase.ROAD_BUILDING:
            roads = self.legal_roads(player)
            if roads:
                self.place_road(player, rng.choice(roads))
            else:
                # Playing the card needs a free edge, so this too only follows an edited state
                self.free_roads_left = 0
                self.turn_phase = self.return_phase
        else:
            if self.trade_offer is not None:
                self.cancel_trade(player)
            self.end_turn(player)

    @recorded("roll_dice", outcome=lambda game, player, total: ({"dice": list(game.dice)}, None))
    def roll_dice(self, player: Optional[Player] = None) -> int:
        self._verify_active()
        player = player or self.get_current_player()
        if not self._is_current(player):
            raise ValueError("It is not your turn.")
        if self.turn_phase != TurnPhase.ROLL_DICE:
            raise ValueError("Cannot roll dice in this phase.")

        d1 = self.rng.randint(1, 6)
        d2 = self.rng.randint(1, 6)
        self.dice_roll = d1 + d2
        self.dice = [d1, d2]
        self.roll_counts[self.dice_roll - DICE_TOTALS.start] += 1
        self._log(f"{player.name} rolled {self.dice_roll}.")

        if self.dice_roll == 7:
            self.return_phase = TurnPhase.MAIN_PHASE
            self._start_robber_sequence()
        else:
            self.turn_phase = TurnPhase.MAIN_PHASE
            self.distribute_resources(self.dice_roll)

        return self.dice_roll

    def _start_robber_sequence(self):
        self.pending_discards = {
            p.color: p.card_count() // 2
            for p in self.players if p.card_count() > self.settings.discard_limit
        }
        self.turn_phase = TurnPhase.DISCARD if self.pending_discards else TurnPhase.MOVE_ROBBER

    def bank_count(self, resource: ResourceType) -> int:
        """Every card is either in a hand or in the bank."""
        held = sum(p.resources[resource] for p in self.players)
        return max(BANK_SIZE - held, 0)

    def distribute_resources(self, roll_number: int):
        payouts: Dict[ResourceType, Dict[PlayerColor, int]] = {}

        for tile in self.board.tiles.values():
            if tile.number != roll_number:
                continue

            # ROBBER LOGIC
            if tile.hex_coords == self.robber_hex:
                continue

            if tile.resource == ResourceType.DESERT:
                continue

            for direction in range(6):
                building = self.settlements.get(Vertex(tile.hex_coords, direction))
                if building:
                    amount = 2 if building.type == BuildingType.CITY else 1
                    shares = payouts.setdefault(tile.resource, {})
                    shares[building.owner] = shares.get(building.owner, 0) + amount

        for resource, shares in payouts.items():
            self._pay_out(resource, shares)

    def _pay_out(self, resource: ResourceType, shares: Dict[PlayerColor, int]):
        """
        When the bank cannot pay everyone, nobody gets that resource. A single
        receiver still takes whatever is left.
        """
        available = self.bank_count(resource)
        if sum(shares.values()) > available and len(shares) > 1:
            self._log(f"The bank has too little {resource.value} to pay out.")
            return
        for color, amount in shares.items():
            self.get_player_by_color(color).add_resource(resource, min(amount, available))

    @recorded("discard", lambda game, cards: {"cards": cards_json(cards)})
    def discard(self, player: Player, cards: Dict[ResourceType, int]):
        self._verify_active()
        if self.turn_phase != TurnPhase.DISCARD:
            raise ValueError("There is nothing to discard right now.")

        required = self.pending_discards.get(player.color, 0)
        if required == 0:
            raise ValueError("You do not have to discard.")
        if any(amount < 0 for amount in cards.values()):
            raise ValueError("Cannot discard a negative amount of cards.")
        if sum(cards.values()) != required:
            raise ValueError(f"You must discard exactly {required} cards.")
        if not player.has_resources(cards):
            raise ValueError("You do not have those cards.")

        player.deduct_resources(cards)
        del self.pending_discards[player.color]
        self._log(f"{player.name} discarded {required} cards.")

        if not self.pending_discards:
            self.turn_phase = TurnPhase.MOVE_ROBBER

    @recorded("move_robber", lambda game, target_hex: {"hex": hex_json(target_hex)})
    def move_robber(self, player: Player, target_hex: Hex):
        self._verify_turn(player, TurnPhase.MOVE_ROBBER)
        if target_hex == self.robber_hex:
             raise ValueError("Robber must be moved to a new location.")
        if target_hex not in self.board.tiles:
            raise ValueError("Invalid hex coordinates.")
        if target_hex not in self.legal_robber_hexes(player):
            raise ValueError(FRIENDLY_ROBBER_ERROR)

        self.robber_hex = target_hex
        self._log(f"{player.name} moved the robber.")
        self.turn_phase = TurnPhase.STEAL if self.steal_victims(player) else self.return_phase

    def steal_victims(self, thief: Player) -> List[Player]:
        """Opponents with cards and a building on the robber hex."""
        if self.robber_hex is None:
            return []
        return [
            p for p in self.players
            if p.color != thief.color and p.card_count() > 0 and self._has_building_on_robber(p)
            and not self._is_protected(thief, p)
        ]

    def _is_protected(self, thief: Player, player: Player) -> bool:
        """
        The friendly robber spares opponents who are far behind. Only the points
        everyone can see count, so hidden cards cannot give a player away.
        """
        return (
            self.settings.friendly_robber and player.color != thief.color
            and player.victory_points <= FRIENDLY_ROBBER_MAX_POINTS
        )

    def _owners_around(self, h: Hex) -> Set[PlayerColor]:
        vertices = [Vertex(h, d).get_canonical() for d in range(6)]
        return {self.settlements[v].owner for v in vertices if v in self.settlements}

    def _has_building_on_robber(self, player: Player) -> bool:
        return player.color in self._owners_around(self.robber_hex)

    @recorded(
        "steal",
        lambda game, victim: {"victim_seat": game.seat_of(victim)},
        # Only the thief and the victim learn which card changed hands
        lambda game, thief, stolen, victim: ({"resource": stolen.value}, sorted([game.seat_of(thief), game.seat_of(victim)])),
    )
    def steal_resource(self, thief: Player, victim: Player):
        self._verify_turn(thief, TurnPhase.STEAL)

        if self.robber_hex is None:
            raise ValueError("Robber is not placed on the board.")

        if thief.color == victim.color:
            raise ValueError("Cannot steal from yourself.")

        # 1. Validate geometric proximity to Robber
        if not self._has_building_on_robber(victim):
            raise ValueError("Victim has no building on the robber hex.")

        # 2. Execute Steal
        if victim.card_count() == 0:
            raise ValueError("Victim has no resources to steal.")
        if self._is_protected(thief, victim):
            raise ValueError(FRIENDLY_ROBBER_ERROR)

        pool = []
        for res, count in victim.resources.items():
            pool.extend([res] * count)

        stolen_res = self.rng.choice(pool)

        victim.remove_resource(stolen_res, 1)
        thief.add_resource(stolen_res, 1)
        self._log(f"{thief.name} stole a card from {victim.name}.")
        self.turn_phase = self.return_phase

        return stolen_res

    # --- Building Logic ---

    @recorded("build_road", lambda game, edge, free=False: corner_json(edge))
    def place_road(self, player: Player, edge: Edge, free: bool = False):
        """
        Handles placement of a road.
        In SETUP phase, checks for 'setup_waiting_for_road' state.
        """
        self._verify_active()
        # Phase Check
        if self.turn_phase == TurnPhase.SETUP:
            self._verify_setup_player(player)
            if not self.setup_waiting_for_road:
                raise ValueError("You must place a settlement first in the setup phase.")
            free = True # Force free in setup
        elif self.turn_phase == TurnPhase.ROAD_BUILDING:
            self._verify_turn(player, TurnPhase.ROAD_BUILDING)
            free = True
        elif not free:
            self._verify_turn(player)

        canonical_edge = edge.get_canonical()
        self._verify_road_location(player, canonical_edge)

        if not free and not player.has_resources(ROAD_COST):
            raise ValueError("Insufficient resources for a road.")

        if not free:
            player.deduct_resources(ROAD_COST)

        self.roads[canonical_edge] = player.color
        self._log(f"{player.name} built a road.")
        self._update_longest_road()

        # Logic for auto-ending turn in SETUP phase after road is placed
        if self.turn_phase == TurnPhase.SETUP:
            self.next_turn()
            return
        if self.turn_phase == TurnPhase.ROAD_BUILDING:
            self.free_roads_left -= 1
            self._finish_road_building_if_done(player)
        self._check_victory()

    def _finish_road_building_if_done(self, player: Player):
        if self.free_roads_left == 0 or not self._free_road_edges(player):
            self.free_roads_left = 0
            self.turn_phase = self.return_phase

    def _verify_road_location(self, player: Player, canonical_edge: Edge):
        if not self.board.is_on_board(canonical_edge):
            raise ValueError("This edge is not on the board.")

        if canonical_edge in self.roads:
            raise ValueError("This edge is already occupied.")

        if self._count_roads(player) >= MAX_ROADS:
            raise ValueError(f"You have no roads left (limit {MAX_ROADS}).")

        if self.turn_phase == TurnPhase.SETUP and self.setup_waiting_for_road:
            if self.setup_last_vertex not in canonical_edge.get_vertices():
                raise ValueError("The road must touch the settlement you just placed.")

        if not self._has_road_connectivity(player, canonical_edge):
             raise ValueError("Road must be connected to your existing network.")

    @recorded("build_settlement", lambda game, vertex, free=False: corner_json(vertex))
    def place_settlement(self, player: Player, vertex: Vertex, free: bool = False):
        """
        Handles placement of a settlement.
        In SETUP phase, ensures player isn't supposed to be placing a road.
        """
        self._verify_active()
        # Phase Check
        if self.turn_phase == TurnPhase.SETUP:
            self._verify_setup_player(player)
            if self.setup_waiting_for_road:
                raise ValueError("You must place a road to finish your setup turn.")
            free = True
        elif not free:
            self._verify_turn(player)

        canonical_vertex = vertex.get_canonical()
        self._verify_settlement_location(player, canonical_vertex, free)

        if not free and not player.has_resources(SETTLEMENT_COST):
            raise ValueError("Insufficient resources for a settlement.")

        if not free:
            player.deduct_resources(SETTLEMENT_COST)

        self.settlements[canonical_vertex] = Building(player.color, BuildingType.SETTLEMENT)
        player.victory_points += 1
        self._log(f"{player.name} built a settlement.")

        # SETUP PHASE: Handle State Transition & Initial Resources
        if self.turn_phase == TurnPhase.SETUP:
            # Give resources if this is the SECOND settlement (Snake Draft Rule)
            # A player has 2 settlements total in setup. If they now have 2, this was the second one.
            player_buildings = [b for b in self.settlements.values() if b.owner == player.color]
            if len(player_buildings) == 2:
                self._give_initial_resources(player, canonical_vertex)

            # Now wait for road
            self.setup_waiting_for_road = True
            self.setup_last_vertex = canonical_vertex

        # A new settlement may cut an opponent's road in two
        self._update_longest_road()
        self._check_victory()

    def _verify_settlement_location(self, player: Player, canonical_vertex: Vertex, free: bool):
        if not self.board.is_on_board(canonical_vertex):
            raise ValueError("This intersection is not on the board.")

        if canonical_vertex in self.settlements:
            raise ValueError("This intersection is already occupied.")

        neighbors = canonical_vertex.get_adjacent_vertices()
        for n in neighbors:
            if n in self.settlements:
                raise ValueError("Distance Rule: Cannot build next to another settlement.")

        if self._count_buildings(player, BuildingType.SETTLEMENT) >= MAX_SETTLEMENTS:
            raise ValueError(f"You have no settlements left (limit {MAX_SETTLEMENTS}).")

        if not free:
            if not self._has_settlement_connectivity(player, canonical_vertex):
                 raise ValueError("Settlement must be connected to your road.")

    @recorded("upgrade_city", lambda game, vertex: corner_json(vertex))
    def upgrade_to_city(self, player: Player, vertex: Vertex):
        self._verify_turn(player)
        canonical_vertex = vertex.get_canonical()

        building = self.settlements.get(canonical_vertex)
        if not building:
            raise ValueError("No settlement at this location.")
        if building.owner != player.color:
            raise ValueError("You can only upgrade your own settlements.")
        if building.type == BuildingType.CITY:
            raise ValueError("This is already a city.")
        if self._count_buildings(player, BuildingType.CITY) >= MAX_CITIES:
            raise ValueError(f"You have no cities left (limit {MAX_CITIES}).")

        if not player.has_resources(CITY_COST):
             raise ValueError("Insufficient resources for a city.")

        player.deduct_resources(CITY_COST)
        building.type = BuildingType.CITY
        player.victory_points += 1
        self._log(f"{player.name} built a city.")
        self._check_victory()

    def trade_rate(self, player: Player, give: ResourceType) -> int:
        """How many cards of `give` the bank wants for one card, given the player's ports."""
        player_ports = self._get_player_ports(player)

        special_port_map = {
            ResourceType.WOOD: PortType.WOOD_2_1,
            ResourceType.BRICK: PortType.BRICK_2_1,
            ResourceType.SHEEP: PortType.SHEEP_2_1,
            ResourceType.WHEAT: PortType.WHEAT_2_1,
            ResourceType.ORE: PortType.ORE_2_1
        }

        if special_port_map.get(give) in player_ports:
            return 2
        if PortType.GENERIC_3_1 in player_ports:
            return 3
        return 4

    @recorded("trade_with_bank", lambda game, give, get: {"give": give.value, "get": get.value})
    def trade_with_bank(self, player: Player, give: ResourceType, get: ResourceType):
        self._verify_turn(player)

        if give not in TRADABLE_RESOURCES or get not in TRADABLE_RESOURCES:
            raise ValueError("That resource cannot be traded.")
        if give == get:
            raise ValueError("You must trade for a different resource.")

        cost = self.trade_rate(player, give)

        if player.resources[give] < cost:
            raise ValueError(f"Not enough {give.value}. Need {cost} (Rate {cost}:1).")
        if self.bank_count(get) == 0:
            raise ValueError(f"The bank has no {get.value} left.")

        player.remove_resource(give, cost)
        player.add_resource(get, 1)
        self._log(f"{player.name} traded {cost} {give.value} for 1 {get.value}.")

    # --- Trade Between Players ---

    @recorded("offer_trade", lambda game, give, get: {"give": cards_json(give), "get": cards_json(get)})
    def offer_trade(self, player: Player, give: Dict[ResourceType, int], get: Dict[ResourceType, int]):
        self._verify_turn(player)
        if not give or not get:
            raise ValueError("A trade needs cards on both sides.")
        if any(n <= 0 for n in (*give.values(), *get.values())):
            raise ValueError("Cannot trade a negative amount of cards.")
        if set(give) & set(get):
            raise ValueError("You cannot ask for the resource you are giving.")
        if any(r not in TRADABLE_RESOURCES for r in (*give, *get)):
            raise ValueError("That resource cannot be traded.")
        if not player.has_resources(give):
            raise ValueError("You do not have those cards.")

        self.trade_offer = TradeOffer(player.color, give, get)
        self._log(f"{player.name} offers a trade.")

    @recorded("respond_trade", lambda game, accept: {"accept": accept})
    def respond_to_trade(self, player: Player, accept: bool):
        self._verify_active()
        offer = self.trade_offer
        if offer is None:
            raise ValueError("There is no trade offer.")
        if player.color == offer.proposer:
            raise ValueError("You cannot answer your own offer.")
        if accept and not player.has_resources(offer.get):
            raise ValueError("You do not have the cards for this trade.")

        for answers in (offer.accepted, offer.declined):
            if player.color in answers:
                answers.remove(player.color)
        (offer.accepted if accept else offer.declined).append(player.color)

    @recorded("confirm_trade", lambda game, partner: {"partner_seat": game.seat_of(partner)})
    def confirm_trade(self, player: Player, partner: Player):
        self._verify_turn(player)
        offer = self.trade_offer
        if offer is None:
            raise ValueError("There is no trade offer.")
        if partner.color not in offer.accepted:
            raise ValueError("That player has not accepted the offer.")
        # The offer may be old: both hands could have changed since it was made
        if not player.has_resources(offer.give) or not partner.has_resources(offer.get):
            raise ValueError("The cards for this trade are no longer available.")

        player.deduct_resources(offer.give)
        partner.deduct_resources(offer.get)
        for resource, amount in offer.give.items():
            partner.add_resource(resource, amount)
        for resource, amount in offer.get.items():
            player.add_resource(resource, amount)
        self.trade_offer = None
        self._log(f"{player.name} traded with {partner.name}.")

    @recorded("cancel_trade")
    def cancel_trade(self, player: Player):
        self._verify_active()
        if self.trade_offer is None or self.trade_offer.proposer != player.color:
            raise ValueError("You have no open offer.")
        self.trade_offer = None

    # --- Development Cards ---

    @recorded(
        "buy_dev_card",
        # The card stays secret from the others until it is played
        outcome=lambda game, player, _: ({"card": player.new_dev_cards[-1].value}, [game.seat_of(player)]),
    )
    def buy_dev_card(self, player: Player):
        self._verify_turn(player)
        if not self.dev_deck:
            raise ValueError("There are no development cards left.")
        if not player.has_resources(DEV_CARD_COST):
            raise ValueError("Insufficient resources for a development card.")

        player.deduct_resources(DEV_CARD_COST)
        player.new_dev_cards.append(self.dev_deck.pop())
        self._log(f"{player.name} bought a development card.")
        self._check_victory()

    def _spend_dev_card(self, player: Player, card: DevCard):
        """A card can be played before or after rolling, one per turn."""
        self._verify_active()
        if not self._is_current(player):
            raise ValueError("It is not your turn.")
        if self.turn_phase not in (TurnPhase.ROLL_DICE, TurnPhase.MAIN_PHASE):
            raise ValueError(PHASE_ERRORS[self.turn_phase])
        if self.dev_card_played:
            raise ValueError("You have already played a development card this turn.")
        if card not in player.dev_cards:
            if card in player.new_dev_cards:
                raise ValueError("You cannot play a card in the turn you bought it.")
            raise ValueError("You do not have that card.")

        player.dev_cards.remove(card)
        self.dev_card_played = True

    @recorded("play_knight")
    def play_knight(self, player: Player):
        self._spend_dev_card(player, DevCard.KNIGHT)
        player.knights_played += 1
        self._log(f"{player.name} played a Knight.")
        self._update_largest_army(player)
        self.return_phase = self.turn_phase
        self.turn_phase = TurnPhase.MOVE_ROBBER
        self._check_victory()

    @recorded("play_road_building")
    def play_road_building(self, player: Player):
        if not self._free_road_edges(player):
            raise ValueError("You have nowhere to build a road.")
        self._spend_dev_card(player, DevCard.ROAD_BUILDING)
        self._log(f"{player.name} played Road Building.")
        self.free_roads_left = ROAD_BUILDING_ROADS
        self.return_phase = self.turn_phase
        self.turn_phase = TurnPhase.ROAD_BUILDING

    @recorded("play_year_of_plenty", lambda game, first, second: {"first": first.value, "second": second.value})
    def play_year_of_plenty(self, player: Player, first: ResourceType, second: ResourceType):
        wanted = [first, second]
        if any(r not in TRADABLE_RESOURCES for r in wanted):
            raise ValueError("That resource cannot be taken.")
        if any(self.bank_count(r) < wanted.count(r) for r in wanted):
            raise ValueError("The bank does not have those cards.")

        self._spend_dev_card(player, DevCard.YEAR_OF_PLENTY)
        for resource in wanted:
            player.add_resource(resource, 1)
        self._log(f"{player.name} played Year of Plenty.")

    @recorded("play_monopoly", lambda game, resource: {"resource": resource.value})
    def play_monopoly(self, player: Player, resource: ResourceType):
        if resource not in TRADABLE_RESOURCES:
            raise ValueError("That resource cannot be taken.")

        self._spend_dev_card(player, DevCard.MONOPOLY)
        taken = 0
        for other in self.players:
            if other.color != player.color:
                taken += other.resources[resource]
                other.resources[resource] = 0
        player.add_resource(resource, taken)
        self._log(f"{player.name} played Monopoly on {resource.value} and took {taken}.")

    def _update_largest_army(self, player: Player):
        """The first to 3 knights holds it; a challenger must have strictly more."""
        holder = self.largest_army_holder
        if holder == player.color or player.knights_played < LARGEST_ARMY_MIN_KNIGHTS:
            return
        if holder is not None:
            previous = self.get_player_by_color(holder)
            if player.knights_played <= previous.knights_played:
                return
            previous.victory_points -= LARGEST_ARMY_POINTS
        player.victory_points += LARGEST_ARMY_POINTS
        self.largest_army_holder = player.color
        self._log(f"{player.name} has the Largest Army ({player.knights_played}).")

    # --- Legal Moves ---

    def legal_settlements(self, player: Player) -> List[Vertex]:
        if self.is_game_over or not self._is_current(player):
            return []
        if self.turn_phase == TurnPhase.SETUP:
            if self.setup_waiting_for_road:
                return []
            free = True
        elif self.turn_phase == TurnPhase.MAIN_PHASE:
            if not player.has_resources(SETTLEMENT_COST):
                return []
            free = False
        else:
            return []
        return [
            v for v in self.board.vertices()
            if self._passes(self._verify_settlement_location, player, v, free)
        ]

    def legal_roads(self, player: Player) -> List[Edge]:
        if self.is_game_over or not self._is_current(player):
            return []
        if self.turn_phase == TurnPhase.SETUP:
            if not self.setup_waiting_for_road:
                return []
        elif self.turn_phase == TurnPhase.ROAD_BUILDING:
            return self._free_road_edges(player)
        elif self.turn_phase != TurnPhase.MAIN_PHASE or not player.has_resources(ROAD_COST):
            return []
        return self._free_road_edges(player)

    def _free_road_edges(self, player: Player) -> List[Edge]:
        return [
            e for e in self.board.edges()
            if self._passes(self._verify_road_location, player, e)
        ]

    def can_buy_dev_card(self, player: Player) -> bool:
        return (
            not self.is_game_over and self._is_current(player)
            and self.turn_phase == TurnPhase.MAIN_PHASE
            and bool(self.dev_deck) and player.has_resources(DEV_CARD_COST)
        )

    def playable_dev_cards(self, player: Player) -> List[DevCard]:
        if (
            self.is_game_over or not self._is_current(player) or self.dev_card_played
            or self.turn_phase not in (TurnPhase.ROLL_DICE, TurnPhase.MAIN_PHASE)
        ):
            return []
        playable = sorted(set(player.dev_cards) - {DevCard.VICTORY_POINT}, key=lambda c: c.value)
        if DevCard.ROAD_BUILDING in playable and not self._free_road_edges(player):
            playable.remove(DevCard.ROAD_BUILDING)
        return playable

    def legal_cities(self, player: Player) -> List[Vertex]:
        if (
            self.is_game_over or not self._is_current(player)
            or self.turn_phase != TurnPhase.MAIN_PHASE
            or not player.has_resources(CITY_COST)
            or self._count_buildings(player, BuildingType.CITY) >= MAX_CITIES
        ):
            return []
        return [
            v for v, b in self.settlements.items()
            if b.owner == player.color and b.type == BuildingType.SETTLEMENT
        ]

    def legal_robber_hexes(self, player: Player) -> List[Hex]:
        if self.is_game_over or not self._is_current(player) or self.turn_phase != TurnPhase.MOVE_ROBBER:
            return []
        hexes = [h for h in self.board.tiles if h != self.robber_hex]
        if not self.settings.friendly_robber:
            return hexes
        allowed = [
            h for h in hexes
            if self.board.tiles[h].resource == ResourceType.DESERT
            or not any(self._is_protected(player, self.get_player_by_color(c)) for c in self._owners_around(h))
        ]
        # When everyone is protected the robber still has to move somewhere
        return allowed or hexes

    @staticmethod
    def _passes(check, *args) -> bool:
        try:
            check(*args)
            return True
        except ValueError:
            return False

    # --- Helpers ---

    def _log(self, message: str):
        self.log = (self.log + [message])[-LOG_SIZE:]

    def _is_current(self, player: Player) -> bool:
        return player.color == self.get_current_player().color

    def _verify_active(self):
        if self.is_game_over:
            raise ValueError("The game is over.")

    def _verify_setup_player(self, player: Player):
        if not self._is_current(player):
            raise ValueError("It is not your turn.")

    def _verify_turn(self, player: Player, phase: TurnPhase = TurnPhase.MAIN_PHASE):
        self._verify_active()
        if not self._is_current(player):
            raise ValueError("It is not your turn.")
        if self.turn_phase != phase:
            raise ValueError(PHASE_ERRORS[self.turn_phase])

    def _check_victory(self):
        p = self.get_current_player()
        if not self.is_game_over and p.victory_points + p.hidden_points() >= self.settings.victory_points:
            self.is_game_over = True
            self.winner = p
            self._log(f"{p.name} won the game!")

    def _count_roads(self, player: Player) -> int:
        return sum(1 for color in self.roads.values() if color == player.color)

    def _count_buildings(self, player: Player, building_type: BuildingType) -> int:
        return sum(
            1 for b in self.settlements.values()
            if b.owner == player.color and b.type == building_type
        )

    def _update_longest_road(self):
        """
        Reassigns the Longest Road award (5+ segments, worth 2 points).
        The holder keeps it on a tie; if a broken road leaves several other
        players tied for first, the award is set aside until one of them leads.
        """
        self.road_lengths = {p.color: self._check_longest_road(p) for p in self.players}
        best = max(self.road_lengths.values())
        holder = self.longest_road_holder

        if best < LONGEST_ROAD_MIN_LENGTH:
            new_holder = None
        elif holder is not None and self.road_lengths[holder] == best:
            new_holder = holder
        else:
            leaders = [color for color, length in self.road_lengths.items() if length == best]
            new_holder = leaders[0] if len(leaders) == 1 else None

        if new_holder == holder:
            return
        if holder is not None:
            self.get_player_by_color(holder).victory_points -= LONGEST_ROAD_POINTS
        if new_holder is not None:
            new_owner = self.get_player_by_color(new_holder)
            new_owner.victory_points += LONGEST_ROAD_POINTS
            self._log(f"{new_owner.name} has the Longest Road ({best}).")
        self.longest_road_holder = new_holder

    def _check_longest_road(self, player: Player) -> int:
        player_edges = [e for e, color in self.roads.items() if color == player.color]

        max_length = 0

        for start_edge in player_edges:
            for start_vertex in start_edge.get_vertices():
                length = self._longest_path_from(start_vertex, player.color, frozenset())
                if length > max_length:
                    max_length = length

        return max_length

    def _longest_path_from(self, vertex: Vertex, color: PlayerColor, used: frozenset) -> int:
        """Longest simple trail leaving `vertex`; an opponent's building stops it."""
        building = self.settlements.get(vertex)
        if used and building and building.owner != color:
            return 0

        best = 0
        for edge in vertex.get_touching_edges():
            if self.roads.get(edge) != color or edge in used:
                continue
            first, second = edge.get_vertices()
            other = second if first == vertex else first
            best = max(best, 1 + self._longest_path_from(other, color, used | {edge}))
        return best

    def _has_road_connectivity(self, player: Player, edge: Edge) -> bool:
        """
        Check if road is connected to own settlement OR own road.
        An opponent's building on a vertex blocks the connection through it.
        """
        for v in edge.get_vertices():
            building = self.settlements.get(v)
            if building:
                if building.owner == player.color:
                    return True
                continue

            for touching in v.get_touching_edges():
                if touching != edge and self.roads.get(touching) == player.color:
                    return True

        return False

    def _has_settlement_connectivity(self, player: Player, vertex: Vertex) -> bool:
        touching_edges = vertex.get_touching_edges()
        for e in touching_edges:
            if self.roads.get(e) == player.color:
                return True
        return False

    def _give_initial_resources(self, player: Player, vertex: Vertex):
        """
        Setup Phase: Give 1 resource for each tile adjacent to the settlement.
        """
        # Identify the 3 hexes touching this vertex
        hexes = [
            vertex.owner,
            vertex.owner.neighbor(vertex.direction),
            vertex.owner.neighbor((vertex.direction - 1) % 6)
        ]

        for h in hexes:
            tile = self.board.get_tile(h)
            if tile and tile.resource != ResourceType.DESERT and self.bank_count(tile.resource) > 0:
                player.add_resource(tile.resource, 1)

    def _get_player_ports(self, player: Player) -> Set[PortType]:
        owned_ports = set()
        for port in self.board.ports:
            for v in port.valid_vertices:
                canon_v = v.get_canonical()
                if canon_v in self.settlements:
                    if self.settlements[canon_v].owner == player.color:
                        owned_ports.add(port.type)
                        break
        return owned_ports
