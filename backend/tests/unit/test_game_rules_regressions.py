import pytest
from unittest.mock import patch

from app.models.board import PortType, Port, ResourceType
from app.models.game import Building, BuildingType, GameState, TurnPhase
from app.models.hex_lib import Edge, Hex, Vertex
from app.services.serializer import GameSerializer

CENTER = Hex(0, 0, 0)
ALL_CARDS = {
    ResourceType.WOOD: 1, ResourceType.BRICK: 1, ResourceType.WHEAT: 1,
    ResourceType.SHEEP: 1, ResourceType.ORE: 1,
}


def main_phase_game(*names):
    game = GameState.create_new_game(list(names or ("Alice", "Bob")))
    game.turn_phase = TurnPhase.MAIN_PHASE
    game.setup_queue = []
    return game


def add_road_path(game, player, length):
    """Walks along the coast so the path never touches itself."""
    coast = game.board._coastal_edges_in_order(game.board)
    for edge in coast[:length]:
        game.roads[edge] = player.color
    return coast


class TestTurnFlow:
    def test_cannot_end_turn_in_setup(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        queue = list(game.setup_queue)

        with pytest.raises(ValueError, match="setup"):
            game.end_turn(game.players[0])

        assert game.setup_queue == queue

    def test_cannot_end_turn_before_rolling(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        game.turn_phase = TurnPhase.ROLL_DICE

        with pytest.raises(ValueError, match="roll the dice"):
            game.end_turn(game.players[0])

        assert game.current_turn_index == 0

    def test_cannot_end_turn_of_another_player(self):
        game = main_phase_game()

        with pytest.raises(ValueError, match="not your turn"):
            game.end_turn(game.players[1])

    def test_cannot_roll_for_another_player(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        game.turn_phase = TurnPhase.ROLL_DICE

        with pytest.raises(ValueError, match="not your turn"):
            game.roll_dice(game.players[1])

    def test_setup_actions_check_the_player(self):
        game = GameState.create_new_game(["Alice", "Bob"])

        with pytest.raises(ValueError, match="not your turn"):
            game.place_settlement(game.players[1], Vertex(CENTER, 0))

    def test_no_actions_after_game_over(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.resources.update(ALL_CARDS)
        game.is_game_over = True

        with pytest.raises(ValueError, match="game is over"):
            game.end_turn(alice)
        with pytest.raises(ValueError, match="game is over"):
            game.place_settlement(alice, Vertex(CENTER, 0), free=True)
        with pytest.raises(ValueError, match="game is over"):
            game.place_road(alice, Edge(CENTER, 0), free=True)
        with pytest.raises(ValueError, match="game is over"):
            game.roll_dice(alice)


class TestBoardValidation:
    def test_settlement_outside_board_is_rejected(self):
        game = main_phase_game()

        with pytest.raises(ValueError, match="not on the board"):
            game.place_settlement(game.players[0], Vertex(Hex(5, -5, 0), 0), free=True)

    def test_road_outside_board_is_rejected(self):
        game = main_phase_game()

        with pytest.raises(ValueError, match="not on the board"):
            game.place_road(game.players[0], Edge(Hex(5, -5, 0), 0), free=True)

    def test_coastal_positions_are_on_the_board(self):
        game = main_phase_game()

        assert game.board.is_on_board(Vertex(Hex(2, 0, -2), 0))
        assert game.board.is_on_board(Edge(Hex(2, 0, -2), 0))


class TestSetupRoad:
    def test_road_must_touch_the_settlement_just_placed(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice, bob = game.players

        first = Vertex(CENTER, 0)
        game.place_settlement(alice, first)
        game.place_road(alice, first.get_touching_edges()[0])

        for vertex in (Vertex(Hex(-2, 2, 0), 3), Vertex(Hex(2, -2, 0), 0)):
            game.place_settlement(bob, vertex)
            game.place_road(bob, vertex.get_touching_edges()[0])

        game.place_settlement(alice, Vertex(Hex(-2, 0, 2), 3))

        # Connected to Alice's first road, but not to her newest settlement
        road_next_to_first = next(
            e for e in first.get_touching_edges()[0].get_connected_edges()
            if e not in game.roads
        )
        with pytest.raises(ValueError, match="settlement you just placed"):
            game.place_road(alice, road_next_to_first)

    def test_setup_road_requirement_survives_serialization(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        vertex = Vertex(CENTER, 0)
        game.place_settlement(game.players[0], vertex)

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.setup_last_vertex == vertex


class TestDistanceRule:
    def test_second_settlement_next_to_opponent_across_the_spoke(self):
        """Regression for the bug from the last commit."""
        game = GameState.create_new_game(["Alice", "Bob"])
        alice, bob = game.players

        vertex = Vertex(CENTER, 0)
        game.place_settlement(alice, vertex)
        game.place_road(alice, vertex.get_touching_edges()[0])

        with pytest.raises(ValueError, match="Distance Rule"):
            game.place_settlement(bob, Vertex(CENTER.neighbor(0), 5))


class TestSeven:
    @staticmethod
    def roll_seven(game):
        game.turn_phase = TurnPhase.ROLL_DICE
        with patch('random.randint', side_effect=[3, 4]):
            game.roll_dice(game.get_current_player())

    def test_players_over_limit_must_discard_half_rounded_down(self):
        game = main_phase_game()
        alice, bob = game.players
        alice.add_resource(ResourceType.WOOD, 9)
        bob.add_resource(ResourceType.WOOD, 7)

        self.roll_seven(game)

        assert game.turn_phase == TurnPhase.DISCARD
        assert game.pending_discards == {alice.color: 4}

    def test_robber_waits_until_everyone_discarded(self):
        game = main_phase_game()
        alice, bob = game.players
        alice.add_resource(ResourceType.WOOD, 8)
        bob.add_resource(ResourceType.BRICK, 8)
        self.roll_seven(game)

        with pytest.raises(ValueError, match="discard"):
            game.move_robber(alice, CENTER)

        game.discard(alice, {ResourceType.WOOD: 4})
        assert game.turn_phase == TurnPhase.DISCARD
        game.discard(bob, {ResourceType.BRICK: 4})

        assert game.turn_phase == TurnPhase.MOVE_ROBBER
        assert alice.card_count() == 4

    @pytest.mark.parametrize("cards, message", [
        ({ResourceType.WOOD: 3}, "exactly 4"),
        ({ResourceType.WOOD: 5}, "exactly 4"),
        ({ResourceType.BRICK: 4}, "do not have"),
        ({ResourceType.WOOD: 5, ResourceType.BRICK: -1}, "negative"),
    ])
    def test_invalid_discards(self, cards, message):
        game = main_phase_game()
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD, 8)
        self.roll_seven(game)

        with pytest.raises(ValueError, match=message):
            game.discard(alice, cards)

        assert alice.card_count() == 8

    def test_player_without_duty_cannot_discard(self):
        game = main_phase_game()
        alice, bob = game.players
        alice.add_resource(ResourceType.WOOD, 8)
        bob.add_resource(ResourceType.WOOD, 2)
        self.roll_seven(game)

        with pytest.raises(ValueError, match="do not have to discard"):
            game.discard(bob, {ResourceType.WOOD: 1})

    def test_cannot_build_or_end_turn_before_robber_moved(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.resources.update(ALL_CARDS)
        self.roll_seven(game)

        with pytest.raises(ValueError, match="move the robber"):
            game.end_turn(alice)
        with pytest.raises(ValueError, match="move the robber"):
            game.place_road(alice, Edge(CENTER, 0))
        with pytest.raises(ValueError, match="move the robber"):
            game.trade_with_bank(alice, ResourceType.WOOD, ResourceType.ORE)

    def test_robber_must_change_hex(self):
        game = main_phase_game()
        alice = game.players[0]
        self.roll_seven(game)

        with pytest.raises(ValueError, match="new location"):
            game.move_robber(alice, game.robber_hex)
        with pytest.raises(ValueError, match="Invalid hex"):
            game.move_robber(alice, Hex(5, -5, 0))

    def test_moving_robber_without_victims_returns_to_main_phase(self):
        game = main_phase_game()
        alice = game.players[0]
        self.roll_seven(game)

        target = next(h for h in game.board.tiles if h != game.robber_hex)
        game.move_robber(alice, target)

        assert game.turn_phase == TurnPhase.MAIN_PHASE

    def test_moving_robber_next_to_opponent_requires_steal(self):
        game = main_phase_game()
        alice, bob = game.players
        target = Hex(2, -2, 0)
        game.robber_hex = CENTER
        game.settlements[Vertex(target, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
        bob.add_resource(ResourceType.ORE, 1)
        self.roll_seven(game)

        game.move_robber(alice, target)
        assert game.turn_phase == TurnPhase.STEAL
        with pytest.raises(ValueError, match="choose a player"):
            game.end_turn(alice)

        game.steal_resource(alice, bob)

        assert game.turn_phase == TurnPhase.MAIN_PHASE
        assert alice.resources[ResourceType.ORE] == 1
        assert bob.card_count() == 0

    def test_opponent_without_cards_is_not_a_victim(self):
        game = main_phase_game()
        alice, bob = game.players
        target = Hex(2, -2, 0)
        game.robber_hex = CENTER
        game.settlements[Vertex(target, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
        self.roll_seven(game)

        game.move_robber(alice, target)

        assert game.turn_phase == TurnPhase.MAIN_PHASE

    def test_robber_blocks_production(self):
        game = main_phase_game()
        alice = game.players[0]
        tile = next(t for t in game.board.tiles.values() if t.number)
        game.settlements[Vertex(tile.hex_coords, 0).get_canonical()] = Building(alice.color, BuildingType.SETTLEMENT)
        game.robber_hex = tile.hex_coords

        for other in game.board.tiles.values():
            if other is not tile:
                other.number = None
        game.distribute_resources(tile.number)

        assert alice.card_count() == 0

    def test_robber_state_survives_serialization(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD, 8)
        self.roll_seven(game)

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.turn_phase == TurnPhase.DISCARD
        assert loaded.pending_discards == {alice.color: 4}


class TestLongestRoad:
    def test_y_junction_is_not_a_single_path(self):
        """Regression: the search could double back through the junction."""
        game = main_phase_game()
        alice = game.players[0]
        for edge in Vertex(CENTER, 0).get_touching_edges():
            game.roads[edge] = alice.color

        assert game._check_longest_road(alice) == 2

    def test_loop_counts_each_segment_once(self):
        game = main_phase_game()
        alice = game.players[0]
        for direction in range(6):
            game.roads[Edge(CENTER, direction).get_canonical()] = alice.color

        assert game._check_longest_road(alice) == 6

    def test_award_gives_two_points_at_five_segments(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)
        coast = add_road_path(game, alice, 4)
        start = coast[0].get_vertices()[0]
        game.settlements[start] = Building(alice.color, BuildingType.SETTLEMENT)
        game._update_longest_road()
        assert game.longest_road_holder is None

        game.place_road(alice, coast[4])

        assert game.longest_road_holder == alice.color
        assert alice.victory_points == 2

    def test_challenger_needs_a_longer_road(self):
        game = main_phase_game()
        alice, bob = game.players
        coast = game.board._coastal_edges_in_order(game.board)
        for edge in coast[:5]:
            game.roads[edge] = alice.color
        game._update_longest_road()

        for edge in coast[10:15]:
            game.roads[edge] = bob.color
        game._update_longest_road()
        assert game.longest_road_holder == alice.color

        game.roads[coast[15]] = bob.color
        game._update_longest_road()

        assert game.longest_road_holder == bob.color
        assert alice.victory_points == 0
        assert bob.victory_points == 2

    def test_opponent_settlement_breaks_the_award(self):
        game = main_phase_game()
        alice, bob = game.players
        coast = add_road_path(game, alice, 5)
        game._update_longest_road()
        assert alice.victory_points == 2

        middle = set(coast[2].get_vertices()) & set(coast[3].get_vertices())
        game.place_settlement(bob, middle.pop(), free=True)

        assert game.longest_road_holder is None
        assert alice.victory_points == 0

    def test_longest_road_can_win_the_game(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.victory_points = 8
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)
        coast = add_road_path(game, alice, 4)
        game.settlements[coast[0].get_vertices()[0]] = Building(alice.color, BuildingType.SETTLEMENT)

        game.place_road(alice, coast[4])

        assert game.is_game_over
        assert game.winner == alice

    def test_award_survives_serialization(self):
        game = main_phase_game()
        alice = game.players[0]
        add_road_path(game, alice, 5)
        game._update_longest_road()

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.longest_road_holder == alice.color


class TestPieceLimits:
    def test_road_limit(self):
        game = main_phase_game()
        alice = game.players[0]
        coast = add_road_path(game, alice, 15)

        with pytest.raises(ValueError, match="no roads left"):
            game.place_road(alice, coast[15], free=True)

    def test_settlement_limit(self):
        game = main_phase_game()
        alice = game.players[0]
        free_vertices = sorted(game.board.vertices(), key=repr)
        placed = 0
        for vertex in free_vertices:
            if placed == 5:
                break
            if not any(n in game.settlements for n in vertex.get_adjacent_vertices()):
                game.place_settlement(alice, vertex, free=True)
                placed += 1

        target = next(
            v for v in free_vertices
            if v not in game.settlements
            and not any(n in game.settlements for n in v.get_adjacent_vertices())
        )
        with pytest.raises(ValueError, match="no settlements left"):
            game.place_settlement(alice, target, free=True)

    def test_city_limit(self):
        game = main_phase_game()
        alice = game.players[0]
        vertices = [Vertex(Hex(q, r, -q - r), 0).get_canonical() for q, r in ((-2, 0), (0, -2), (2, -2), (0, 0))]
        for vertex in vertices:
            game.settlements[vertex] = Building(alice.color, BuildingType.CITY)
        target = Vertex(Hex(0, 2, -2), 1).get_canonical()
        game.settlements[target] = Building(alice.color, BuildingType.SETTLEMENT)
        alice.add_resource(ResourceType.ORE, 3)
        alice.add_resource(ResourceType.WHEAT, 2)

        with pytest.raises(ValueError, match="no cities left"):
            game.upgrade_to_city(alice, target)

    def test_upgrading_returns_a_settlement_piece(self):
        game = main_phase_game()
        alice = game.players[0]
        vertex = Vertex(CENTER, 0).get_canonical()
        game.settlements[vertex] = Building(alice.color, BuildingType.SETTLEMENT)
        alice.add_resource(ResourceType.ORE, 3)
        alice.add_resource(ResourceType.WHEAT, 2)

        game.upgrade_to_city(alice, vertex)

        assert game._count_buildings(alice, BuildingType.SETTLEMENT) == 0


class TestRoadBlocking:
    def test_opponent_building_interrupts_connectivity(self):
        game = main_phase_game()
        alice, bob = game.players
        vertex = Vertex(CENTER, 0).get_canonical()
        road, onward = [e for e in vertex.get_touching_edges()][:2]
        game.roads[road] = alice.color
        game.settlements[vertex] = Building(bob.color, BuildingType.SETTLEMENT)
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)

        with pytest.raises(ValueError, match="must be connected"):
            game.place_road(alice, onward)

    def test_own_building_keeps_connectivity(self):
        game = main_phase_game()
        alice = game.players[0]
        vertex = Vertex(CENTER, 0).get_canonical()
        road, onward = [e for e in vertex.get_touching_edges()][:2]
        game.roads[road] = alice.color
        game.settlements[vertex] = Building(alice.color, BuildingType.SETTLEMENT)
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)

        game.place_road(alice, onward)

        assert game.roads[onward] == alice.color


class TestTrade:
    def give_port(self, game, player, port_type):
        vertex = Vertex(CENTER, 0).get_canonical()
        game.board.ports = [Port(port_type, [vertex])]
        game.settlements[vertex] = Building(player.color, BuildingType.SETTLEMENT)

    def test_specific_port_rate_applies_only_to_its_resource(self):
        game = main_phase_game()
        alice = game.players[0]
        self.give_port(game, alice, PortType.ORE_2_1)
        alice.add_resource(ResourceType.ORE, 2)
        alice.add_resource(ResourceType.WOOD, 3)

        game.trade_with_bank(alice, ResourceType.ORE, ResourceType.BRICK)
        assert alice.resources[ResourceType.ORE] == 0
        assert alice.resources[ResourceType.BRICK] == 1

        with pytest.raises(ValueError, match="Need 4"):
            game.trade_with_bank(alice, ResourceType.WOOD, ResourceType.BRICK)

    def test_specific_port_beats_generic_port(self):
        game = main_phase_game()
        alice = game.players[0]
        self.give_port(game, alice, PortType.ORE_2_1)
        game.board.ports.append(Port(PortType.GENERIC_3_1, list(game.settlements)))

        assert game.trade_rate(alice, ResourceType.ORE) == 2
        assert game.trade_rate(alice, ResourceType.WOOD) == 3

    def test_cannot_trade_for_the_same_resource(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.add_resource(ResourceType.ORE, 4)

        with pytest.raises(ValueError, match="different resource"):
            game.trade_with_bank(alice, ResourceType.ORE, ResourceType.ORE)

    def test_cannot_trade_desert(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.add_resource(ResourceType.ORE, 4)

        with pytest.raises(ValueError, match="cannot be traded"):
            game.trade_with_bank(alice, ResourceType.ORE, ResourceType.DESERT)


class TestVictory:
    def test_city_can_end_the_game(self):
        game = main_phase_game()
        alice = game.players[0]
        vertex = Vertex(CENTER, 0).get_canonical()
        game.settlements[vertex] = Building(alice.color, BuildingType.SETTLEMENT)
        alice.victory_points = 9
        alice.add_resource(ResourceType.ORE, 3)
        alice.add_resource(ResourceType.WHEAT, 2)

        game.upgrade_to_city(alice, vertex)

        assert game.is_game_over
        assert game.winner == alice

    def test_points_gained_off_turn_win_on_own_turn(self):
        game = main_phase_game()
        alice, bob = game.players
        bob.victory_points = 10

        assert not game.is_game_over
        game.end_turn(alice)

        assert game.is_game_over
        assert game.winner == bob
