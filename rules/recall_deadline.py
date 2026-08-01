from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class RecallDeadlineRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="RecallDeadline", priority=AlertPriority.CRITICAL, cooldown=10.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        opp = game_state.get("my_opponent")

        if opp:
            is_dead = bool(opp.get("isDead", False))
            timer = float(opp.get("respawnTimer", 0.0))

            if is_dead and 0 < timer <= 8.0:
                if "recall" not in triggered_events:
                    triggered_events.add("recall")
                    return {
                        "id": 0.0,
                        "priority": int(self.priority),
                        "title": "RECALL DEADLINE",
                        "text": "Opponent respawning in 8s!",
                        "speech": "Recall deadline.",
                        "sound": "alert",
                    }
            elif not is_dead:
                # Discard the tag once they are alive so it can fire again next time they die
                triggered_events.discard("recall")

        return None
