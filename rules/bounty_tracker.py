from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class BountyTrackerRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="BountyTracker", priority=AlertPriority.INFO, cooldown=150.0)
        self.threat_threshold = 3.5  # Minimum score to be considered a "Bounty"

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        enemies = game_state.get("enemy_team_stats", [])
        if not enemies:
            return None

        highest_threat_player = None
        max_score = 0.0

        for enemy in enemies:
            scores = enemy.get("scores", {})
            kills = float(scores.get("kills", 0))
            deaths = float(scores.get("deaths", 0))
            assists = float(scores.get("assists", 0))
            cs = float(scores.get("creepScore", 0))

            threat_score = (kills - deaths) + (assists * 0.3) + (cs * 0.02)

            if threat_score > max_score:
                max_score = threat_score
                highest_threat_player = enemy

        # If the scariest enemy on the map exceeds our threshold
        if highest_threat_player and max_score >= self.threat_threshold:
            role = highest_threat_player.get("position", "UNKNOWN")
            champ = highest_threat_player.get("championName", "Unknown")

            # Floor the score to group alerts (e.g., threat level 4 vs 5)
            threat_tier = int(max_score)
            event_tag = f"bounty_target_{role}_{threat_tier}"

            if event_tag not in triggered_events:
                triggered_events.add(event_tag)

                # Format a clean lane name (BOTTOM -> Bot, TOP -> Top)
                lane_name = role.capitalize() if role != "UNKNOWN" else champ

                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "SHUTDOWN AVAILABLE",
                    "text": f"Enemy {lane_name} ({champ}) has a high bounty. Path for shutdown gold.",
                    "speech": f"High value target. The enemy {lane_name} has a bounty.",
                    "sound": "alert",
                }

        return None
