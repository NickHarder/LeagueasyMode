import importlib
import inspect
import os
import pkgutil

import yaml

from engine.event_bus import AlertPriority, EventBus, TacticalRule


def load_all_rules(bus: EventBus) -> None:
    """Dynamically discovers, configures, and registers rules."""

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "rules_config.yaml",
    )

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print("[WARNING] rules_config.yaml not found. Using default rule behaviors.")
        config = {}

    rule_configs = config.get("rules", {})

    for _, module_name, _ in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f".{module_name}", package=__name__)

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, TacticalRule) and obj is not TacticalRule:
                rule_prefs = rule_configs.get(name, {})
                is_enabled = rule_prefs.get("enabled", True)

                if not is_enabled:
                    print(f"[ENGINE] Skipping {name} (Disabled in config)")
                    continue

                try:
                    rule = obj()  # type: ignore

                    if "priority" in rule_prefs:
                        rule.priority = AlertPriority(int(rule_prefs["priority"]))

                    if "cooldown" in rule_prefs:
                        rule.cooldown = float(rule_prefs["cooldown"])

                    bus.register(rule)

                except Exception as e:
                    print(f"[ERROR] Failed to load rule '{name}': {e}")
