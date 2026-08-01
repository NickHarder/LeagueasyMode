from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class CannonWaveRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="CannonWaves", priority=AlertPriority.INFO, cooldown=30.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        my_role = game_state.get("my_role", "UNKNOWN")

        # Only evaluate for laners pre-15 minutes
        if my_role in {"TOP", "MID", "BOTTOM", "SUPPORT"} and 0 < t < 900:
            cannon_idx = int((t - 20) / 90)
            next_alert_time = 110 + (cannon_idx * 90)
            event_tag = f"cannon_{cannon_idx}"

            if next_alert_time <= t < (next_alert_time + 5) and event_tag not in triggered_events:
                triggered_events.add(event_tag)
                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "RECALL WINDOW",
                    "text": "Cannon wave spawns in 15s. Crash and base.",
                    "speech": "Optimal recall window opening.",
                    "sound": "chime",
                }

        return None
