from typing import Any, TypedDict

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class ObjectiveInfo(TypedDict):
    spawn_time: float
    name: str


class ObjectiveSyncRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="ObjectiveSync", priority=AlertPriority.CRITICAL, cooldown=60.0)

        # Separated timers: Drake at 5:00 (300s), Grubs at 8:00 (480s), Herald at 15:00 (900s), Baron at 20:00 (1200s)
        self.static_spawns: dict[str, ObjectiveInfo] = {
            "first_dragon": {"spawn_time": 300.0, "name": "First Dragon"},
            "first_grubs": {"spawn_time": 480.0, "name": "Void Grubs"},
            "rift_herald": {"spawn_time": 900.0, "name": "Rift Herald"},
            "first_baron": {"spawn_time": 1200.0, "name": "Baron Nashor"},
        }

        self.lookahead = 55.0  # Warn 55 seconds before spawn

    def evaluate(
        self,
        game_state: dict[str, Any],
        triggered_events: set[str],
    ) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)

        # 1. Check Static First-Spawns (Early/Mid Game)
        for key, objective in self.static_spawns.items():
            spawn_t = objective["spawn_time"]
            name = objective["name"]

            # If we are in the 55-second lookahead window
            if spawn_t - self.lookahead <= t < spawn_t:
                event_tag = f"obj_spawn_{key}"

                if event_tag not in triggered_events:
                    triggered_events.add(event_tag)
                    return {
                        "id": 0.0,
                        "priority": int(self.priority),
                        "title": "MACRO SYNC",
                        "text": f"{name} spawning in 55s. Secure priority.",
                        "speech": f"{name} spawns in 55 seconds. Decide your pathing now.",
                        "sound": "alert",
                    }

        # 2. Check Dynamic Respawns (Mid/Late Game)
        # Default next drake to 300 so it aligns with the first spawn
        next_drake = game_state.get("next_dragon_time", 300.0)
        next_baron = game_state.get("next_baron_time", 1200.0)

        # Dynamic Dragon (Avoid double-pinging the 5:00 first spawn)
        if next_drake > 300.0 and (next_drake - self.lookahead <= t < next_drake):
            event_tag = f"dyn_spawn_drake_{int(next_drake)}"
            if event_tag not in triggered_events:
                triggered_events.add(event_tag)
                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "DRAGON SYNC",
                    "text": "Dragon respawns in 55s. Setup vision.",
                    "speech": "Dragon respawns in 55 seconds. Establish vision control.",
                    "sound": "alert",
                }

        # Dynamic Baron (Avoid double-pinging the 20:00 first spawn)
        if next_baron > 1200.0 and (next_baron - self.lookahead <= t < next_baron):
            event_tag = f"dyn_spawn_baron_{int(next_baron)}"
            if event_tag not in triggered_events:
                triggered_events.add(event_tag)
                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "BARON SYNC",
                    "text": "Baron Nashor respawns in 55s.",
                    "speech": "Baron spawns in 55 seconds. Sweep the pit.",
                    "sound": "alert",
                }

        return None
