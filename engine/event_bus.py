import time
from enum import IntEnum
from typing import Any, TypedDict

# ======================================================================================
# TYPES & SCHEMAS
# ======================================================================================


class AlertPriority(IntEnum):
    CRITICAL = 1
    TACTICAL = 2
    INFO = 3


class AlertMsg(TypedDict):
    id: float
    priority: int
    title: str
    text: str
    speech: str
    sound: str


# ======================================================================================
# RULE BASE CLASS
# ======================================================================================


class TacticalRule:
    """The base class for all rules."""

    def __init__(self, name: str, priority: AlertPriority, cooldown: float = 30.0):
        self.name = name
        self.priority = priority
        self.cooldown = cooldown
        self.last_triggered = 0.0

    def evaluate(self, game_state: dict[str, Any], triggered_events: set[str]) -> AlertMsg | None:
        """
        Evaluates the current game state and returns an AlertMsg if conditions are met.

        `triggered_events` is a shared set used to ensure one-off alerts (like hitting level 2)
        only fire exactly once per game.
        """
        raise NotImplementedError("Rules must implement the evaluate method.")


# ======================================================================================
# EVENT BUS
# ======================================================================================


class EventBus:
    """
    The traffic cop. It holds all registered rules, passes the state to them,
    and returns a sorted list of generated alerts based on priority.
    """

    def __init__(self) -> None:
        self.rules: list[TacticalRule] = []
        self.triggered_events: set[str] = set()

    def register(self, rule: TacticalRule) -> None:
        self.rules.append(rule)
        print(f"[ENGINE] Registered Rule: {rule.name}")

    def evaluate_all(self, game_state: dict[str, Any]) -> list[AlertMsg]:
        alerts = []
        now = time.time()
        t = game_state.get("game_time", 0.0)

        # If game time is less than 5 seconds, it's a brand new game.
        if t < 5.0 and len(self.triggered_events) > 0:
            self.triggered_events.clear()
            for rule in self.rules:
                rule.last_triggered = 0.0
            print("[SYSTEM] New match detected. Wiped alert history and cooldowns.")

        for rule in self.rules:
            if now - rule.last_triggered >= rule.cooldown:
                try:
                    alert = rule.evaluate(game_state, self.triggered_events)
                    if alert:
                        rule.last_triggered = now
                        alert["id"] = time.time()
                        alert["priority"] = int(alert.get("priority", rule.priority))
                        alerts.append(alert)
                except Exception as e:
                    print(f"[ERROR] Rule '{rule.name}' crashed during evaluation: {e}")

        # Sort by priority (CRITICAL = 1, TACTICAL = 2, INFO = 3)
        return sorted(alerts, key=lambda x: x["priority"])
