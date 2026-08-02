import os
from typing import Any

import yaml

from engine.event_bus import AlertMsg, AlertPriority, TacticalRule


class GoldBreakpointRule(TacticalRule):
    def __init__(self) -> None:
        super().__init__(name="GoldBreakpoints", priority=AlertPriority.INFO, cooldown=15.0)
        self.cached_build: list[dict[str, Any]] = []
        self.is_loaded = False

    def _load_build(self, champion: str, role: str) -> None:
        """Locates the champion file and parses the target build for the current role."""
        base_dir = os.path.dirname(os.path.dirname(__file__))

        # Normalize champion name (e.g., "Jarvan IV" -> "JarvanIV")
        clean_champ = champion.replace(" ", "")
        champ_file = os.path.join(base_dir, "champions", f"{clean_champ}.yaml")
        default_file = os.path.join(base_dir, "champions", "default.yaml")

        data: dict[str, Any] = {}

        # 1. Try loading champion-specific file
        if os.path.exists(champ_file):
            try:
                with open(champ_file) as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"[ERROR] Failed to load {champ_file}: {e}")

        # 2. Extract role data or fallback if missing
        role_data = data.get(role, {})
        if not role_data and os.path.exists(default_file):
            try:
                with open(default_file) as f:
                    default_data = yaml.safe_load(f) or {}
                    role_data = default_data.get(role, {}) or default_data.get("JUNGLE", {})
            except Exception as e:
                print(f"[ERROR] Failed to load {default_file}: {e}")

        if not role_data:
            print(f"[ENGINE] No build configuration found for {champion} ({role}).")
            self.is_loaded = True
            return

        active_build_name = role_data.get("default_build")
        builds = role_data.get("builds", {})

        self.cached_build = builds.get(active_build_name, [])
        self.is_loaded = True
        print(f"[ENGINE] Loaded {champion} {role} build: {active_build_name}")

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        my_gold = game_state.get("my_gold")
        my_champ = game_state.get("my_champion")
        my_role = game_state.get("my_role")
        my_items = game_state.get("my_items", set())

        if my_gold is None or not my_champ or not my_role or my_role == "UNKNOWN":
            return None

        if not self.is_loaded:
            self._load_build(str(my_champ), str(my_role))

        if not self.cached_build:
            return None

        target_item = None

        # Iterate through the build path to find the next unowned target item
        for i, target in enumerate(self.cached_build):
            item_name = target["item"]

            if item_name in my_items:
                continue

            # Skip situational items if a subsequent build item was already purchased
            bought_later = any(b["item"] in my_items for b in self.cached_build[i + 1 :])
            is_situational = target.get("situational", False)

            if bought_later and is_situational:
                continue

            target_item = target
            break

        if not target_item:
            return None

        item_name = target_item["item"]
        item_cost = target_item["cost"]
        priority = target_item.get("priority", "normal")

        buy_tag = f"buy_{item_name}"
        greed_tag = f"greed_{item_name}"

        # 1. Player can afford the item outright
        if my_gold >= item_cost and buy_tag not in triggered_events:
            triggered_events.add(buy_tag)
            return {
                "id": 0.0,
                "priority": int(self.priority),
                "title": "ITEM SPIKE",
                "text": f"Can afford {item_name} ({item_cost}g)",
                "speech": f"You can afford {item_name}. Consider a recall.",
                "sound": "chime",
            }

        # 2. Greed window (High-priority items within a 150g deficit)
        deficit = item_cost - my_gold
        if 0 < deficit <= 150 and priority == "high" and greed_tag not in triggered_events:
            triggered_events.add(greed_tag)
            return {
                "id": 0.0,
                "priority": int(AlertPriority.TACTICAL),
                "title": "GREED WINDOW",
                "text": f"Need {deficit}g for {item_name}.",
                "speech": f"You are {deficit} gold short of {item_name}. Greed one more camp before recalling.",
                "sound": "chime",
            }

        return None
