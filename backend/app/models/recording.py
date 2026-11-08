"""
Records every action the rules engine accepts, in the same JSON form the
client sends, plus the outcome of any chance it involved. A game record is
these events in order (see docs/game-record.md), and replaying them through
apply_action rebuilds the game exactly.
"""
import functools
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

Payload = Callable[..., Dict[str, Any]]
# Called with the game, the player, the method's result and its arguments. Returns
# the outcome and the seats that saw it (None means everyone did).
Outcome = Callable[..., Tuple[Dict[str, Any], Optional[List[int]]]]


def hex_json(h) -> Dict[str, int]:
    return {"q": h.q, "r": h.r, "s": h.s}


def corner_json(position) -> Dict[str, Any]:
    """
    A vertex or an edge: a hex it belongs to and a direction from 0 to 5. Of
    the equivalent forms, the canonical one is written, so the same corner is
    always spelled the same way.
    """
    position = position.get_canonical()
    return {"hex": hex_json(position.owner), "direction": position.direction}


def cards_json(cards) -> Dict[str, int]:
    return {resource.value: amount for resource, amount in cards.items()}


def recorded(action: str, payload: Payload = lambda game: {}, outcome: Optional[Outcome] = None):
    """
    Marks a public GameState method as an action. When the call succeeds and
    is not nested in another recorded call, it appends one event to
    game.events. A call that raises records nothing, so a refused action
    leaves no trace.
    """
    def wrap(method):
        signature = inspect.signature(method)

        @functools.wraps(method)
        def call(game, *args, **kwargs):
            # Callers pass arguments by position or by name, so bind them first:
            # the first one is the player, the rest describe the action
            bound = signature.bind(game, *args, **kwargs)
            bound.apply_defaults()
            _, player, *rest = bound.arguments.values()
            player = player or game.get_current_player()
            turn = game.turn_number
            game._record_depth += 1
            try:
                result = method(game, *args, **kwargs)
            finally:
                game._record_depth -= 1
            if game._record_depth == 0:
                event: Dict[str, Any] = {
                    "turn": turn,
                    "seat": game.seat_of(player),
                    "action": action,
                    "payload": payload(game, *rest),
                }
                if outcome is not None:
                    event["outcome"], seen_by = outcome(game, player, result, *rest)
                    if seen_by is not None:
                        event["visible_to"] = seen_by
                if game._auto:
                    event["auto"] = True
                game.events.append(event)
            return result
        return call
    return wrap
