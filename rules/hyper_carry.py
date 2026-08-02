from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule

HYPER_CARRIES = {"Kayle", "Kassadin", "Smolder", "Vayne", "Vladimir"}


class HyperCarryRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="HyperCarry", priority=AlertPriority.CRITICAL, cooldown=120.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        opp = game_state.get("my_opponent")

        if opp:
            name = opp.get("summonerName", "")
            champ = opp.get("championName", "")
            lvl = int(opp.get("level", 1))
            event_tag = f"lvl16_{name}"

            if lvl >= 16 and event_tag not in triggered_events and champ in HYPER_CARRIES:
                triggered_events.add(event_tag)
                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "LATE GAME THREAT",
                    "text": f"Hyper-carry {champ} hit Level 16!",
                    "speech": f"Alert. {champ} has reached level 16.",
                    "sound": "alert",
                }

        return None
