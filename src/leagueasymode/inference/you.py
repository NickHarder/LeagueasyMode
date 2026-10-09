"""You (estimator 13): facts about your build and pace, from your own exact numbers.

- **What to build against them:** for armor, magic resist and health, the effective health a
  hundred gold of it buys you now, against the enemy's damage mix (`fights.py`). Effective
  health is health over the share of their damage that gets through (100 / (100 + resistance)
  of each kind), so its rise per point is worked out exactly; each stat's price is the patch's
  basic item for it (Cloth Armor, Null-Magic Mantle, Ruby Crystal), first guesses without them.
- **Holding gold:** how long your unspent gold has stayed at 1,300 or more while you are alive,
  about a component and a ward, a first guess.
- **Creep score pace:** yours a minute this game, against yours a minute over your recent games
  on Summoner's Rift, from the League client.
"""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.data_dragon import ItemStatBonuses, PatchStats
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.combat_stats import combat_stats_of
from leagueasymode.inference.fights import fighter_damage, fighter_of
from leagueasymode.inference.gold import NEW_GAME_SLACK_SECONDS, player_key
from leagueasymode.overlay_state import CombatStats, DefenseValue, YouPanel
from leagueasymode.patch_data import ItemCatalog
from leagueasymode.player_intel import PlayerRecord, PlayerRecords

type DefensiveStat = Literal["armor", "magic_resist", "health"]

RESISTANCE_SCALE: Final = 100.0
SECONDS_PER_MINUTE: Final = 60.0
HUNDRED_GOLD: Final = 100.0
# The patch's basic item for each defensive stat.
BASIC_ITEM_IDS: Final[Mapping[DefensiveStat, int]] = {
    "armor": 1029,
    "magic_resist": 1033,
    "health": 1028,
}


class YouRules(BaseModel):
    """The You panel's thresholds, and each stat's price without the patch's items.

    `tuning.json`'s "you".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    holding_gold_threshold: float = 1300.0
    # Creep score a minute is shown from this time; before it, too little has died.
    creep_pace_from_seconds: float = 180.0
    # Gold a point: Cloth Armor 300 for 15, Null-Magic Mantle 450 for 25, Ruby Crystal 400 for
    # 150, as in recent seasons.
    gold_per_armor: float = 20.0
    gold_per_magic_resist: float = 18.0
    gold_per_health: float = 400.0 / 150.0


YOU_RULES: Final = YouRules()


def defense_values(
    stats: CombatStats,
    enemy_physical_share: float,
    item_catalog: ItemCatalog | None = None,
    patch_stats: PatchStats | None = None,
    rules: YouRules = YOU_RULES,
) -> list[DefenseValue]:
    """Return the effective health a hundred gold of each defensive stat buys, best first.

    Args:
        stats: Your stats.
        enemy_physical_share: The share of the enemy's damage that is physical.
        item_catalog: The patch's items, for each stat's price; None for the first guesses.
        patch_stats: The patch's item stats, for each basic item's amount; None likewise.
        rules: The first guesses.

    Returns:
        A value for armor, magic resist and health, the one that buys the most first.
    """
    physical_through = RESISTANCE_SCALE / (RESISTANCE_SCALE + max(stats.armor, 0.0))
    magic_through = RESISTANCE_SCALE / (RESISTANCE_SCALE + max(stats.magic_resist, 0.0))
    taken_share = (
        enemy_physical_share * physical_through + (1 - enemy_physical_share) * magic_through
    )
    # The rise of health / taken_share per point of each stat.
    rise_per_point: dict[DefensiveStat, float] = {
        "armor": stats.health
        * enemy_physical_share
        * physical_through**2
        / RESISTANCE_SCALE
        / taken_share**2,
        "magic_resist": stats.health
        * (1 - enemy_physical_share)
        * magic_through**2
        / RESISTANCE_SCALE
        / taken_share**2,
        "health": 1 / taken_share,
    }
    values = [
        DefenseValue(
            stat=stat,
            effective_health_per_hundred_gold=round(
                rise * HUNDRED_GOLD / gold_per_point(stat, item_catalog, patch_stats, rules), 1
            ),
        )
        for stat, rise in rise_per_point.items()
    ]
    return sorted(values, key=lambda value: value.effective_health_per_hundred_gold, reverse=True)


def gold_per_point(
    stat: DefensiveStat,
    item_catalog: ItemCatalog | None,
    patch_stats: PatchStats | None,
    rules: YouRules = YOU_RULES,
) -> float:
    """Return what a point of a defensive stat costs, by the patch's basic item for it.

    Args:
        stat: The stat.
        item_catalog: The patch's items; None for the first guess.
        patch_stats: The patch's item stats; None for the first guess.
        rules: The first guesses.

    Returns:
        The gold a point.
    """
    first_guess = {
        "armor": rules.gold_per_armor,
        "magic_resist": rules.gold_per_magic_resist,
        "health": rules.gold_per_health,
    }[stat]
    item_id = BASIC_ITEM_IDS[stat]
    item = item_catalog.items_by_id.get(item_id) if item_catalog is not None else None
    bonuses = patch_stats.item_bonuses(item_id) if patch_stats is not None else None
    amount = _amount_of(stat, bonuses) if bonuses is not None else 0.0
    if item is None or item.price_total <= 0 or amount <= 0:
        return first_guess
    return item.price_total / amount


def usual_creep_score_per_minute(record: PlayerRecord) -> float | None:
    """Return a player's creep score a minute over their recent games.

    Args:
        record: Their record from the League client.

    Returns:
        Their creep score over the games' minutes; None without a game.
    """
    minutes = sum(game.duration_seconds for game in record.recent_games) / SECONDS_PER_MINUTE
    if minutes <= 0:
        return None
    return sum(game.creep_score for game in record.recent_games) / minutes


class YouTracker:
    """Follows how long you have held your gold, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self, rules: YouRules = YOU_RULES) -> None:
        """Start with no game.

        Args:
            rules: The threshold of gold held.
        """
        self.rules: Final = rules
        self._holding_since_seconds: float | None = None
        self._last_game_time_seconds = 0.0

    def update(self, snapshot: GameSnapshot) -> float | None:
        """Take in one answer of the game's API, and return how long you have held your gold.

        Args:
            snapshot: The game's state.

        Returns:
            The seconds your unspent gold has stayed at the threshold or more while alive; None
            while it is below, while you are dead, or when spectating.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._holding_since_seconds = None
        self._last_game_time_seconds = game_time_seconds
        active_player = snapshot.active_player
        you = next(
            (player for player in snapshot.players if snapshot.is_active_player(player)), None
        )
        is_holding = (
            active_player is not None
            and you is not None
            and not you.is_dead
            and active_player.current_gold >= self.rules.holding_gold_threshold
        )
        if not is_holding:
            self._holding_since_seconds = None
            return None
        if self._holding_since_seconds is None:
            self._holding_since_seconds = game_time_seconds
        return game_time_seconds - self._holding_since_seconds


def you_panel(
    snapshot: GameSnapshot,
    *,
    holding_gold_seconds: float | None,
    item_catalog: ItemCatalog | None,
    patch_stats: PatchStats | None,
    player_records: PlayerRecords | None,
    rules: YouRules = YOU_RULES,
) -> YouPanel | None:
    """Return the facts about your build and pace.

    Args:
        snapshot: The game's state.
        holding_gold_seconds: How long you have held your gold (`YouTracker`).
        item_catalog: The patch's items; None while unknown.
        patch_stats: The patch's stats, for the enemy's damage; None while unknown.
        player_records: Each player's record from the League client; None while unknown.
        rules: The thresholds.

    Returns:
        The panel; None when spectating.
    """
    active_player = snapshot.active_player
    you = next((player for player in snapshot.players if snapshot.is_active_player(player)), None)
    if active_player is None or you is None:
        return None
    your_stats = combat_stats_of(snapshot, you, patch_stats)
    enemy_physical_share = _enemy_physical_share(snapshot, patch_stats)
    game_time_seconds = snapshot.game_data.game_time_seconds
    your_record = player_records.get(player_key(you)) if player_records is not None else None
    return YouPanel(
        defenses=(
            defense_values(your_stats, enemy_physical_share, item_catalog, patch_stats, rules)
            if your_stats is not None and enemy_physical_share is not None
            else []
        ),
        enemy_physical_share=enemy_physical_share,
        unspent_gold=round(active_player.current_gold),
        holding_gold_seconds=holding_gold_seconds,
        creep_score_per_minute=(
            you.scores.creep_score / (game_time_seconds / SECONDS_PER_MINUTE)
            if game_time_seconds >= rules.creep_pace_from_seconds
            else None
        ),
        usual_creep_score_per_minute=(
            usual_creep_score_per_minute(your_record.record) if your_record is not None else None
        ),
    )


def _enemy_physical_share(snapshot: GameSnapshot, patch_stats: PatchStats | None) -> float | None:
    """Return the share of the enemy team's damage that is physical, the dead counted too.

    Args:
        snapshot: The game's state.
        patch_stats: The patch's stats; None while unknown.

    Returns:
        The share; None while any enemy's stats are unknown, or they deal no damage.
    """
    ally_team = snapshot.ally_team()
    fighters = [
        fighter_of(snapshot, player, patch_stats)
        for player in snapshot.players
        if player.team != ally_team
    ]
    known = [fighter for fighter in fighters if fighter is not None]
    if not known or len(known) != len(fighters):
        return None
    damages = [fighter_damage(fighter) for fighter in known]
    physical = sum(physical for physical, _ in damages)
    total = physical + sum(magic for _, magic in damages)
    return physical / total if total > 0 else None


def _amount_of(stat: DefensiveStat, bonuses: ItemStatBonuses) -> float:
    """Return how much of a defensive stat an item gives.

    Args:
        stat: The stat.
        bonuses: The item's stats.

    Returns:
        The amount.
    """
    return {
        "armor": bonuses.flat_armor,
        "magic_resist": bonuses.flat_magic_resist,
        "health": bonuses.flat_health,
    }[stat]
