from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class EarlyJungleVisionRule(TacticalRule):
    def __init__(self) -> None:
        # 60s cooldown since these are distinct, one-time early game events
        super().__init__(name="EarlyJungleVision", priority=AlertPriority.TACTICAL, cooldown=60.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)

        # 1. Scuttle Prep
        if 155.0 <= t <= 160.0 and "scuttle" not in triggered_events:
            triggered_events.add("scuttle")
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "SCUTTLE PREP",
                "text": "Scuttles spawn at 2:55.",
                "speech": "Scuttles spawning in 20 seconds.",
                "sound": "chime",
            }

        # 2. Level 1 Ward Expiration
        if 170.0 <= t <= 175.0 and "wards" not in triggered_events:
            triggered_events.add("wards")
            return {
                "id": 0.0,
                "priority": int(AlertPriority.INFO),
                "title": "VISION",
                "text": "Level 1 Wards expiring. Gank windows open.",
                "speech": "Early wards expiring.",
                "sound": "chime",
            }

        return None
