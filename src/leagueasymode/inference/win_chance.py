"""Win chance (estimator 12): the chance the player's team wins, from what the game shows now.

A logistic model: each thing that moves a game, from the player's side, adds its weight to the
log-odds of a win. The weights are hand-set first guesses, to refit on recorded games (phase
5.5):

- the gold lead, as a share of what each team has earned, so that a lead counts for less as the
  game's gold grows; early, against a floor rather than the little earned, so that a first kill is
  not a won game. A medium lead at 15:00 (about 2.5k) is set to win about 3 games in 4, a large one
  (about 5k) about 9 in 10, as seasons 7 to 10 did (Esports Tales, "The status of Snowball");
- the level lead, turrets, inhibitors down, dragons, the soul, the Baron and Elder buffs;
- the players alive, which weigh more as death timers grow;
- the blue side, a little ahead in most seasons.

The gold lead is an estimate with a band (`gold.py`), so the chance is averaged over the band rather
than read at its middle: a lead the overlay is unsure of counts for less. For a logistic of a
normal variable the average has no closed form; the probit approximation (MacKay, 1992) is used,
within a percentage point of it.
"""

import math
from dataclasses import dataclass
from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import (
    BAND_STANDARD_DEVIATIONS,
    TURRET_KILLED_EVENT,
    TURRET_NAME_PATTERN,
)
from leagueasymode.inference.objectives import TEAM_BY_NUMBER
from leagueasymode.overlay_state import (
    BuffTimer,
    DragonTimer,
    InhibitorTimer,
    TeamGold,
    TeamItemGold,
    WinChance,
    WinReason,
)

SECONDS_PER_MINUTE: Final = 60.0
ONE_THOUSAND: Final = 1000.0
BLUE_TEAM: Final = "ORDER"
MINUS_SIGN: Final = "\u2212"
SHOWN_REASON_COUNT: Final = 2
# A thing pulling the log-odds by less than this is not named as a reason.
SMALLEST_REASON_EFFECT: Final = 0.05

type Feature = Literal[
    "blue_side",
    "gold_share",
    "level_lead_per_player",
    "turret_lead",
    "inhibitor_lead",
    "dragon_lead",
    "soul",
    "baron",
    "elder",
    "alive_lead_by_time",
]


@dataclass(frozen=True)
class WinChanceRules:
    """The model's weights, each in log-odds per unit of its feature, and how features are scaled.

    First guesses, to refit on recorded games.
    """

    blue_side_weight: float = 0.05
    # Per unit of the gold lead over the gold each team has earned.
    gold_share_weight: float = 10.0
    # The least a team's earned gold counts as, about five players' at 6:00.
    team_gold_floor: float = 12_500.0
    # Per level of lead, per player.
    level_weight: float = 0.3
    turret_weight: float = 0.1
    inhibitor_weight: float = 0.4
    dragon_weight: float = 0.1
    soul_weight: float = 0.5
    baron_weight: float = 0.7
    elder_weight: float = 1.0
    # Per player alive of lead, at 30:00; it grows with the game's time up to its cap.
    alive_weight: float = 0.6
    alive_full_weight_minutes: float = 30.0
    alive_weight_cap: float = 1.5


WIN_CHANCE_RULES: Final = WinChanceRules()
TEAM_SIZE: Final = 5


@dataclass(frozen=True)
class WinFeatures:
    """What the model reads, at one moment, from the player's side."""

    game_minutes: float
    is_blue_side: bool
    # The gold lead (yours minus theirs), its standard deviation, and what a team has earned on
    # average; the lead is 0 when no gold is known.
    gold_lead: float
    gold_lead_deviation: float
    team_gold_scale: float
    # Your team's levels added up, minus theirs.
    level_lead: int
    # Their turrets and inhibitors down, minus yours.
    turret_lead: int
    inhibitor_lead: int
    # Your elemental dragons, minus theirs.
    dragon_lead: int
    # 1 when your team holds the soul or the buff, -1 when theirs does, 0 otherwise.
    soul: int
    baron: int
    elder: int
    ally_alive: int
    enemy_alive: int

    def values(self, rules: WinChanceRules = WIN_CHANCE_RULES) -> dict[Feature, float]:
        """Return each feature's value, as the model weighs it.

        Args:
            rules: How the gold and the players alive are scaled.

        Returns:
            The values by feature.
        """
        return {
            "blue_side": 1.0 if self.is_blue_side else -1.0,
            "gold_share": self.gold_lead / max(self.team_gold_scale, rules.team_gold_floor),
            "level_lead_per_player": self.level_lead / TEAM_SIZE,
            "turret_lead": float(self.turret_lead),
            "inhibitor_lead": float(self.inhibitor_lead),
            "dragon_lead": float(self.dragon_lead),
            "soul": float(self.soul),
            "baron": float(self.baron),
            "elder": float(self.elder),
            "alive_lead_by_time": (self.ally_alive - self.enemy_alive)
            * min(self.game_minutes / rules.alive_full_weight_minutes, rules.alive_weight_cap),
        }


def weights_of(rules: WinChanceRules) -> dict[Feature, float]:
    """Return the model's weight for each feature.

    Args:
        rules: The weights.

    Returns:
        The weights by feature.
    """
    return {
        "blue_side": rules.blue_side_weight,
        "gold_share": rules.gold_share_weight,
        "level_lead_per_player": rules.level_weight,
        "turret_lead": rules.turret_weight,
        "inhibitor_lead": rules.inhibitor_weight,
        "dragon_lead": rules.dragon_weight,
        "soul": rules.soul_weight,
        "baron": rules.baron_weight,
        "elder": rules.elder_weight,
        "alive_lead_by_time": rules.alive_weight,
    }


def win_chance(features: WinFeatures, rules: WinChanceRules = WIN_CHANCE_RULES) -> WinChance:
    """Return the chance the player's team wins, and the two things moving it most.

    Args:
        features: The game now, from the player's side.
        rules: The model's weights.

    Returns:
        The chance, averaged over the gold lead's band, and its reasons.
    """
    values = features.values(rules)
    weights = weights_of(rules)
    effects = {feature: weights[feature] * value for feature, value in values.items()}
    log_odds = sum(effects.values())
    log_odds_deviation = (
        weights["gold_share"]
        * features.gold_lead_deviation
        / max(features.team_gold_scale, rules.team_gold_floor)
    )
    named = sorted(
        (
            (feature, effect)
            for feature, effect in effects.items()
            if feature != "blue_side" and abs(effect) >= SMALLEST_REASON_EFFECT
        ),
        key=lambda entry: abs(entry[1]),
        reverse=True,
    )
    return WinChance(
        ally_chance=_logistic(log_odds / math.sqrt(1 + math.pi * log_odds_deviation**2 / 8)),
        reasons=[
            WinReason(label=_reason_label(feature, features), effect=round(effect, 3))
            for feature, effect in named[:SHOWN_REASON_COUNT]
        ],
    )


def win_features(
    snapshot: GameSnapshot,
    *,
    team_gold: TeamGold | None,
    team_item_gold: TeamItemGold | None,
    dragon: DragonTimer,
    buffs: list[BuffTimer],
    inhibitors: list[InhibitorTimer],
) -> WinFeatures:
    """Return what the model reads from the game now, from the player's side.

    Args:
        snapshot: The game's state.
        team_gold: What each team has earned, estimated; None while unknown.
        team_item_gold: What each team's items are worth, the gold lead's stand-in while the
            earned gold is unknown; None while unknown too.
        dragon: The dragons each team has taken, and the soul.
        buffs: The Baron and Elder buffs running.
        inhibitors: The inhibitors down.

    Returns:
        The features.
    """
    ally_team = snapshot.ally_team()
    allies = [player for player in snapshot.players if player.team == ally_team]
    enemies = [player for player in snapshot.players if player.team != ally_team]
    gold_lead, gold_lead_deviation, team_gold_scale = _gold_lead(team_gold, team_item_gold)
    return WinFeatures(
        game_minutes=snapshot.game_data.game_time_seconds / SECONDS_PER_MINUTE,
        is_blue_side=ally_team == BLUE_TEAM,
        gold_lead=gold_lead,
        gold_lead_deviation=gold_lead_deviation,
        team_gold_scale=team_gold_scale,
        level_lead=sum(player.level for player in allies) - sum(player.level for player in enemies),
        turret_lead=_turret_lead(snapshot, ally_team),
        inhibitor_lead=sum(1 for timer in inhibitors if timer.side == "enemy")
        - sum(1 for timer in inhibitors if timer.side == "ally"),
        dragon_lead=dragon.ally_dragon_count - dragon.enemy_dragon_count,
        soul=_side_sign(dragon.soul_holder),
        baron=sum(_side_sign(buff.holder) for buff in buffs if buff.buff == "baron"),
        elder=sum(_side_sign(buff.holder) for buff in buffs if buff.buff == "elder"),
        ally_alive=sum(1 for player in allies if not player.is_dead),
        enemy_alive=sum(1 for player in enemies if not player.is_dead),
    )


def _gold_lead(
    team_gold: TeamGold | None, team_item_gold: TeamItemGold | None
) -> tuple[float, float, float]:
    """Return the gold lead, its standard deviation, and what a team has earned on average.

    Args:
        team_gold: What each team has earned; None while unknown.
        team_item_gold: What each team's items are worth; None while unknown.

    Returns:
        The three; a lead of 0 when neither is known.
    """
    if team_gold is not None:
        return (
            float(team_gold.ally_total_gold - team_gold.enemy_total_gold),
            team_gold.lead_band_gold / BAND_STANDARD_DEVIATIONS,
            (team_gold.ally_total_gold + team_gold.enemy_total_gold) / 2,
        )
    if team_item_gold is not None:
        return (
            float(team_item_gold.ally_item_gold - team_item_gold.enemy_item_gold),
            0.0,
            (team_item_gold.ally_item_gold + team_item_gold.enemy_item_gold) / 2,
        )
    return 0.0, 0.0, 0.0


def _turret_lead(snapshot: GameSnapshot, ally_team: str) -> int:
    """Return the other team's turrets down, minus the player's team's, from the feed.

    Args:
        snapshot: The game's state.
        ally_team: The player's team.

    Returns:
        The lead in turrets.
    """
    fallen_teams = [
        TEAM_BY_NUMBER[turret_match["team"]]
        for event in snapshot.event_list.events
        if event.event_name == TURRET_KILLED_EVENT
        for turret_match in [TURRET_NAME_PATTERN.match(event.turret_killed_name or "")]
        if turret_match is not None
    ]
    return sum(1 for team in fallen_teams if team != ally_team) - sum(
        1 for team in fallen_teams if team == ally_team
    )


def _side_sign(side: Literal["ally", "enemy"] | None) -> int:
    """Return 1 for the player's team, -1 for the other, 0 for neither.

    Args:
        side: The side, or None.

    Returns:
        The sign.
    """
    return {"ally": 1, "enemy": -1}.get(side or "", 0)


def _reason_label(feature: Feature, features: WinFeatures) -> str:
    """Return a reason in words, from the player's side.

    Args:
        feature: The feature behind it.
        features: The game now.

    Returns:
        Such as "gold +2.1k", "their Baron" or "5v3".
    """
    if feature == "gold_share":
        return f"gold {_signed(features.gold_lead / ONE_THOUSAND, decimals=1)}k"
    if feature == "alive_lead_by_time":
        return f"{features.ally_alive}v{features.enemy_alive}"
    held = {"soul": features.soul, "baron": features.baron, "elder": features.elder}
    if feature in held:
        name = {"soul": "soul", "baron": "Baron", "elder": "Elder"}[feature]
        return name if held[feature] > 0 else f"their {name}"
    lead_name, lead = {
        "level_lead_per_player": ("levels", features.level_lead),
        "turret_lead": ("turrets", features.turret_lead),
        "inhibitor_lead": ("inhibitors", features.inhibitor_lead),
        "dragon_lead": ("dragons", features.dragon_lead),
    }[feature]
    return f"{lead_name} {_signed(lead, decimals=0)}"


def _signed(amount: float, *, decimals: int) -> str:
    """Return an amount with its sign, a true minus sign for a negative one.

    Args:
        amount: The amount.
        decimals: The decimals to show.

    Returns:
        Such as "+2.1", or "3" after a minus sign.
    """
    text = f"{abs(amount):.{decimals}f}"
    return f"+{text}" if amount >= 0 else f"{MINUS_SIGN}{text}"


def _logistic(log_odds: float) -> float:
    """Return the chance of log-odds.

    Args:
        log_odds: The log-odds.

    Returns:
        The chance, from 0 to 1.
    """
    if log_odds < 0:
        # The same, written so that a large negative number does not overflow.
        return math.exp(log_odds) / (1 + math.exp(log_odds))
    return 1 / (1 + math.exp(-log_odds))
