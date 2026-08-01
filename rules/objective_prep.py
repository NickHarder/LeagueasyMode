from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class ObjectivePrepRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="ObjectivePrep", priority=AlertPriority.TACTICAL, cooldown=30.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        drag_time = game_state.get("next_dragon_time", 300.0)

        # Only trigger if the game has progressed past 5 minutes
        if t > 60:
            drag120_tag = f"drag120_{drag_time}"
            drag60_tag = f"drag60_{drag_time}"

            time_until = drag_time - t

            # 2-Minute Warning (Base & Wards)
            if 0 < time_until <= 120.5 and drag120_tag not in triggered_events:
                triggered_events.add(drag120_tag)
                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "VISION PREP",
                    "text": "Dragon in 2 mins. Buy wards.",
                    "speech": "Dragon in 2 minutes. Prepare vision.",
                    "sound": "chime",
                }

            # 1-Minute Warning (Coinflip Check)
            if 0 < time_until <= 60.5 and drag60_tag not in triggered_events:
                triggered_events.add(drag60_tag)

                # Dynamically alter the speech string based on the enemy jungler's state
                jg_alive = game_state.get("enemy_jg_alive", True)
                cf = ". Enemy jungler Alive!" if jg_alive else ". Enemy jungler Dead."

                return {
                    "id": 0.0,
                    "priority": int(AlertPriority.CRITICAL),
                    "title": "OBJECTIVE SPAWN",
                    "text": f"Dragon in 60s{cf}",
                    "speech": f"Dragon in 1 minute{cf}",
                    "sound": "alert",
                }

        return None
