from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class TempoResetRule(TacticalRule):
    MIN_DRAGON_WARNING = 40.0
    MAX_DRAGON_WARNING = 60.0
    MIN_RESET_GOLD = 1000

    def __init__(self) -> None:
        super().__init__(
            name="Tempo Reset",
            priority=AlertPriority.TACTICAL,
            cooldown=30.0,
        )

    def evaluate(
        self,
        game_state: dict[str, Any],
        triggered_events: set[str],
    ) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        next_drag = game_state.get("next_dragon_time", 300.0)
        my_gold = game_state.get("current_gold", 0)

        time_until_drag = next_drag - t
        event_tag = f"tempo_reset_{next_drag}"

        if (
            self.MIN_DRAGON_WARNING <= time_until_drag <= self.MAX_DRAGON_WARNING
            and my_gold >= self.MIN_RESET_GOLD
            and event_tag not in triggered_events
        ):
            triggered_events.add(event_tag)
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "TEMPO DEADLINE",
                "text": f"Unspent gold: {my_gold}. Base now for Dragon.",
                "speech": "Tempo warning. Reset now to contest objective.",
                "sound": "alert",
            }

        return None
