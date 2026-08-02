import math
from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class SmiteEfficiencyRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="SmiteEfficiency", priority=AlertPriority.INFO, cooldown=45.0)
        self.last_cs = 0

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        spells = game_state.get("my_summoner_spells", [])

        # 1. Ensure the player actually has Smite equipped
        if not any("Smite" in s for s in spells):
            return None

        t = game_state.get("game_time", 0.0)
        my_cs = game_state.get("my_cs", 0)

        # Jungle camps don't spawn until 0:55, skip tracking before then
        if t < 55.0:
            self.last_cs = my_cs
            return None

        # Check if player is actively clearing a camp
        actively_clearing = my_cs > self.last_cs
        self.last_cs = my_cs

        # 2. The Smite Metronome (Evaluates every 90s interval)
        window_index = int(math.floor(t / 90.0))
        event_tag = f"smite_tempo_{window_index}"

        # If your CS goes up during a new 90s window, fire the efficiency reminder
        if actively_clearing and event_tag not in triggered_events:
            triggered_events.add(event_tag)
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "SMITE EFFICIENCY",
                "text": "Smite interval reached. Burn a charge on this camp.",
                "speech": "Smite tempo check. Do not hold two charges.",
                "sound": "alert",
            }

        return None
