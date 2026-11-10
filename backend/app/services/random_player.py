"""
A random but legal player, used by the simulation tests and to record sample
games. It prefers moves that score, so its games reach a winner.
"""
import random

from app.models.game import TRADABLE_RESOURCES, GameState, TurnPhase
from app.models.player import DevCard


def play_dev_card(game: GameState, player, rng: random.Random) -> bool:
    playable = game.playable_dev_cards(player)
    if not playable or rng.random() < 0.5:
        return False

    card = rng.choice(playable)
    if card == DevCard.KNIGHT:
        game.play_knight(player)
    elif card == DevCard.ROAD_BUILDING:
        game.play_road_building(player)
    elif card == DevCard.MONOPOLY:
        game.play_monopoly(player, rng.choice(TRADABLE_RESOURCES))
    else:
        available = [r for r in TRADABLE_RESOURCES if game.bank_count(r) >= 2]
        if not available:
            return False
        first = rng.choice(available)
        game.play_year_of_plenty(player, first, first)
    return True


def try_player_trade(game: GameState, player, rng: random.Random) -> bool:
    mine = [r for r in TRADABLE_RESOURCES if player.resources[r] > 0]
    partner = rng.choice([p for p in game.players if p.color != player.color])
    theirs = [r for r in TRADABLE_RESOURCES if partner.resources[r] > 0 and r not in mine]
    if not mine or not theirs:
        return False
    game.offer_trade(player, {rng.choice(mine): 1}, {rng.choice(theirs): 1})
    game.respond_to_trade(partner, True)
    game.confirm_trade(player, partner)
    return True


def play_step(game: GameState, rng: random.Random):
    """Performs one random legal action, preferring ones that score points."""
    if game.turn_phase == TurnPhase.DISCARD:
        color, required = next(iter(game.pending_discards.items()))
        player = game.get_player_by_color(color)
        pool = [r for r, n in player.resources.items() for _ in range(n)]
        cards = {}
        for res in rng.sample(pool, required):
            cards[res] = cards.get(res, 0) + 1
        game.discard(player, cards)
        return

    player = game.get_current_player()

    if game.turn_phase in (TurnPhase.ROLL_DICE, TurnPhase.MAIN_PHASE) and play_dev_card(game, player, rng):
        return

    if game.turn_phase == TurnPhase.ROLL_DICE:
        game.roll_dice(player)
    elif game.turn_phase == TurnPhase.MOVE_ROBBER:
        game.move_robber(player, rng.choice(game.legal_robber_hexes(player)))
    elif game.turn_phase == TurnPhase.STEAL:
        game.steal_resource(player, rng.choice(game.steal_victims(player)))
    elif game.turn_phase == TurnPhase.ROAD_BUILDING:
        game.place_road(player, rng.choice(game.legal_roads(player)))
    elif game.turn_phase == TurnPhase.SETUP:
        if game.setup_waiting_for_road:
            game.place_road(player, rng.choice(game.legal_roads(player)))
        else:
            game.place_settlement(player, rng.choice(game.legal_settlements(player)))
    else:
        if rng.random() < 0.1 and try_player_trade(game, player, rng):
            return
        if game.can_buy_dev_card(player) and rng.random() < 0.5:
            game.buy_dev_card(player)
        elif cities := game.legal_cities(player):
            game.upgrade_to_city(player, rng.choice(cities))
        elif settlements := game.legal_settlements(player):
            game.place_settlement(player, rng.choice(settlements))
        elif (roads := game.legal_roads(player)) and rng.random() < 0.7:
            game.place_road(player, rng.choice(roads))
        else:
            for give in TRADABLE_RESOURCES:
                # The bank can run out of a resource, so only those it still has are asked for
                wanted = [r for r in TRADABLE_RESOURCES if r != give and game.bank_count(r) > 0]
                if wanted and player.resources[give] >= game.trade_rate(player, give):
                    game.trade_with_bank(player, give, rng.choice(wanted))
                    return
            game.end_turn(player)
