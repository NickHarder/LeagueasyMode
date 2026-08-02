from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class CrossMapInvadeRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="CrossMapInvader", priority=AlertPriority.CRITICAL, cooldown=60.0)

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        seen_time = game_state.get("enemy_jg_last_seen_time", 0.0)
        seen_role = game_state.get("enemy_jg_last_seen_role", "UNKNOWN")
        my_role = game_state.get("my_role", "UNKNOWN")

        # Only process if we are playing Jungle and the event just happened (within 15s)
        if my_role != "JUNGLE" or (t - seen_time > 15.0):
            return None

        event_tag = f"cross_map_{int(seen_time)}"
        if event_tag in triggered_events:
            return None

        # If they show Bot/Support, we invade Top.
        if seen_role in ["BOTTOM", "UTILITY"]:
            triggered_events.add(event_tag)
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "CROSS-MAP: ENEMY BOT",
                "text": "Enemy JG is bot. Invade top camps or take Grubs/Herald.",
                "speech": "Enemy jungler spotted bot side. Immediately take their top camps or secure the objective.",
                "sound": "alert",
            }

        # If they show Top, we invade Bot.
        if seen_role == "TOP":
            triggered_events.add(event_tag)
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "CROSS-MAP: ENEMY TOP",
                "text": "Enemy JG is top. Invade bot camps or take Dragon.",
                "speech": "Enemy jungler spotted top side. Instantly invade bot side or start dragon.",
                "sound": "alert",
            }

        return None
