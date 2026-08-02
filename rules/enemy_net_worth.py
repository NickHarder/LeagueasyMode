from typing import Any

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class EnemyNetWorthRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="EnemyNetWorth", priority=AlertPriority.TACTICAL, cooldown=60.0)
        # Standard first-item and second-item gold thresholds
        self.spike_thresholds: list[int] = [1200, 3000, 6000]

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        t = game_state.get("game_time", 0.0)
        enemy_cs = game_state.get("enemy_jg_cs")

        if enemy_cs is None:
            return None

        kills = game_state.get("enemy_jg_kills", 0)
        assists = game_state.get("enemy_jg_assists", 0)

        # 1. Starting Gold
        starting_gold = 500

        # 2. Passive Gold (Starts at 1:50/110s, grants 2.04 gold per second)
        passive_gold = max(0.0, (t - 110.0)) * 2.04

        # 3. Minion/Monster Value (~24g per jungle CS average, 4 CS per camp)
        cs_gold = enemy_cs * 24.0

        # 4. KDA Value (Assuming standard non-bounty values)
        kill_gold = kills * 300.0
        assist_gold = assists * 150.0

        estimated_net_worth = int(starting_gold + passive_gold + cs_gold + kill_gold + assist_gold)

        for threshold in sorted(self.spike_thresholds, reverse=True):
            event_tag = f"enemy_gold_{threshold}"

            if estimated_net_worth >= threshold and event_tag not in triggered_events:
                triggered_events.add(event_tag)

                return {
                    "id": 0.0,
                    "priority": int(self.priority),
                    "title": "ENEMY POWER SPIKE",
                    "text": f"Enemy Jungler est. net worth: {estimated_net_worth}g",
                    "speech": f"Warning. Enemy jungler has generated enough gold for a {threshold} gold power spike.",
                    "sound": "alert",
                }

        return None
