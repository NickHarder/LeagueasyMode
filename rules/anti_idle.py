from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class AntiIdleRule(TacticalRule):
    def __init__(self) -> None:
        # Cooldown of 60s ensures it doesn't spam you if you are in a prolonged teamfight
        super().__init__(name="AntiIdlePacing", priority=AlertPriority.TACTICAL, cooldown=60.0)
        self.last_cs = 0
        self.last_cs_time = 0.0

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        my_cs = game_state.get("my_cs")

        # Bypass tracking before first jungle camps spawn at 0:55
        if t < 55 or my_cs is None:
            self.last_cs_time = t
            return None

        # The moment you kill a camp/minion, reset the internal idle clock
        if my_cs > self.last_cs:
            self.last_cs = my_cs
            self.last_cs_time = t
            return None

        time_since_last_cs = t - self.last_cs_time
        event_tag = f"idle_warning_{int(t)}"

        # 45 seconds of zero CS means you are either dead, or wasting massive tempo
        # waiting in a bush. Either way, it's a great trigger to re-focus on pathing.
        if time_since_last_cs >= 45.0 and event_tag not in triggered_events:
            triggered_events.add(event_tag)

            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "TEMPO BLEED",
                "text": "0 CS in 45 seconds. Stop forcing, return to farming.",
                "speech": "Pacing warning. You have stopped farming.",
                "sound": "alert",
            }

        return None
