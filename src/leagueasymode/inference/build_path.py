"""Build path (estimator 5): each player's likely next finished item, and when they can buy it.

Every finished item of the patch a player does not own yet is a candidate, unless it is boots, for
another champion, or made by an ally. Each is scored by three things, and the scores are turned
into shares of the chance (a softmax):

- **The components they hold** toward it, walking its recipe down: a component held counts at its
  whole price, one not held is looked into for its own parts. The share of the item's price already
  paid weighs most, since a component bought is a build begun.
- **What they built lately**: in their recent games on this champion, the share that ended with
  the item; their games on other champions count half as much.
- **Their champion's class**: the share of the item's stat categories that suit the champion's
  main class, and less so its second.

What is left to pay is the item's price less the components held toward it; the gold tracker's
estimate gives the chance they hold that much now, and their income so far when they will.
"""

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import ScoreboardPlayer
from leagueasymode.inference.gold import GOLD_RULES, chance_of_affording
from leagueasymode.overlay_state import GoldEstimate, NextItemEstimate
from leagueasymode.patch_data import BOOTS_CATEGORY, CatalogItem, ItemCatalog
from leagueasymode.player_intel import PlayerRecord

# The stat categories of the client's items that suit each class. A first guess, to fit on
# recordings.
CLASS_CATEGORIES: Final[Mapping[str, frozenset[str]]] = {
    "Marksman": frozenset({"CriticalStrike", "AttackSpeed", "Damage", "LifeSteal", "OnHit"}),
    "Mage": frozenset(
        {
            "SpellDamage",
            "Mana",
            "ManaRegen",
            "MagicPenetration",
            "AbilityHaste",
            "CooldownReduction",
        }
    ),
    "Assassin": frozenset(
        {"Damage", "ArmorPenetration", "AbilityHaste", "CooldownReduction", "NonbootsMovement"}
    ),
    "Fighter": frozenset(
        {"Damage", "Health", "AbilityHaste", "CooldownReduction", "LifeSteal", "SpellVamp"}
    ),
    "Tank": frozenset({"Health", "Armor", "SpellBlock", "HealthRegen", "Aura"}),
    "Support": frozenset({"Aura", "ManaRegen", "Health", "Active", "Vision", "GoldPer"}),
}
STAT_CATEGORIES: Final = frozenset().union(*CLASS_CATEGORIES.values())
# Summoner's Rift's items have ids below this; other modes' are numbered from it up.
HIGHEST_RIFT_ITEM_ID: Final = 9999
# Income is counted from when passive gold starts, and over at least a minute.
INCOME_STARTS_AT_SECONDS: Final = GOLD_RULES.passive_gold_rates[0][0]
SHORTEST_INCOME_SECONDS: Final = 60.0


@dataclass(frozen=True)
class BuildRules:
    """How much each signal weighs, and how sharply the scores become chances."""

    component_weight: float = 3.0
    history_weight: float = 2.0
    class_weight: float = 1.0
    # How far the main class outweighs the second.
    main_class_share: float = 0.7
    # Games on other champions count this much as games on this one.
    other_champion_history_share: float = 0.5
    sharpness: float = 3.0


BUILD_RULES: Final = BuildRules()


def next_item(
    player: ScoreboardPlayer,
    item_catalog: ItemCatalog | None,
    patch_stats: PatchStats | None,
    *,
    record: PlayerRecord | None = None,
    champion_id: int = 0,
    gold: GoldEstimate | None = None,
    game_time_seconds: float,
    rules: BuildRules = BUILD_RULES,
) -> NextItemEstimate | None:
    """Return a player's likely next finished item.

    Args:
        player: The player.
        item_catalog: The patch's items; None while unknown.
        patch_stats: The patch's stats, for the champion's classes; None while unknown.
        record: Their recent games, for what they built; None when unknown.
        champion_id: The client's id of their champion, to find their games on it.
        gold: Their gold, for the chance to afford it; None while unknown.
        game_time_seconds: The game's clock.
        rules: The weights.

    Returns:
        The item, or None without the catalog or any candidate.
    """
    if item_catalog is None:
        return None
    held = Counter[int]()
    for item in player.items:
        held[item.item_id] += item.count
    candidates = [
        item
        for item in item_catalog.items_by_id.values()
        if _is_candidate(item, player, held, item_catalog)
    ]
    if not candidates:
        return None
    main_classes, second_classes = _classes_of(player, patch_stats)
    invested_golds = [
        _invested_gold(candidate.item_id, Counter(held), item_catalog) for candidate in candidates
    ]
    scores = [
        rules.component_weight * invested_gold / max(candidate.price_total, 1)
        + rules.history_weight * _history_share(candidate.item_id, record, champion_id, rules)
        + rules.class_weight
        * _class_fit(candidate, main_classes, second_classes, rules.main_class_share)
        for candidate, invested_gold in zip(candidates, invested_golds, strict=True)
    ]
    best_index = max(range(len(candidates)), key=scores.__getitem__)
    best_item = candidates[best_index]
    weights_total = sum(
        math.exp(rules.sharpness * (score - scores[best_index])) for score in scores
    )
    remaining_gold = round(best_item.price_total - invested_golds[best_index])
    return NextItemEstimate(
        item_id=best_item.item_id,
        item_name=best_item.name,
        likelihood=1.0 / weights_total,
        remaining_gold=remaining_gold,
        chance_to_afford=chance_of_affording(gold, remaining_gold) if gold is not None else None,
        affordable_at_game_time_seconds=(
            _affordable_at(gold, remaining_gold, game_time_seconds) if gold is not None else None
        ),
    )


def _is_candidate(
    item: CatalogItem, player: ScoreboardPlayer, held: Counter[int], item_catalog: ItemCatalog
) -> bool:
    """Return whether an item could be a player's next finished one.

    Args:
        item: The item.
        player: The player.
        held: Their inventory's counts by item id.
        item_catalog: The patch's items.

    Returns:
        Whether it is a finished Summoner's Rift item in the store, not boots, not owned, and not
        for another champion or made by an ally.
    """
    return (
        item.item_id <= HIGHEST_RIFT_ITEM_ID
        and item_catalog.is_finished(item.item_id)
        and item.is_in_store
        and BOOTS_CATEGORY not in item.categories
        and held[item.item_id] == 0
        and not item.required_ally
        and item.required_champion in {"", player.champion_alias(), player.champion_name}
    )


def _invested_gold(item_id: int, held: Counter[int], item_catalog: ItemCatalog) -> float:
    """Return the gold the held components already put toward an item, using up what they count.

    Args:
        item_id: The item.
        held: The components still free to count; those counted are taken out.
        item_catalog: The patch's items.

    Returns:
        The gold.
    """
    item = item_catalog.items_by_id.get(item_id)
    invested_gold = 0.0
    for component_id in item.builds_from if item is not None else []:
        if held[component_id] > 0:
            held[component_id] -= 1
            invested_gold += item_catalog.total_price(component_id) or 0
        else:
            invested_gold += _invested_gold(component_id, held, item_catalog)
    return invested_gold


def _history_share(
    item_id: int, record: PlayerRecord | None, champion_id: int, rules: BuildRules
) -> float:
    """Return how often a player's recent games ended with an item, those on their champion first.

    Args:
        item_id: The item.
        record: Their recent games; None when unknown.
        champion_id: Their champion's id.
        rules: How much other champions' games count.

    Returns:
        The share, from 0 to 1.
    """
    games = record.recent_games if record is not None else ()
    champion_games = [game for game in games if game.champion_id == champion_id]
    if champion_games:
        return sum(1 for game in champion_games if item_id in game.item_ids) / len(champion_games)
    if not games:
        return 0.0
    other_share = sum(1 for game in games if item_id in game.item_ids) / len(games)
    return rules.other_champion_history_share * other_share


def _classes_of(
    player: ScoreboardPlayer, patch_stats: PatchStats | None
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the stat categories that suit a player's champion's main class and its second.

    Args:
        player: The player.
        patch_stats: The patch's stats; None while unknown.

    Returns:
        Both sets; empty when unknown.
    """
    tags = (
        patch_stats.champion_tags(player.raw_champion_name, player.champion_name)
        if patch_stats is not None
        else ()
    )
    main_tag = tags[0] if tags else ""
    second_tag = tags[1] if len(tags) > 1 else ""
    return (
        CLASS_CATEGORIES.get(main_tag, frozenset()),
        CLASS_CATEGORIES.get(second_tag, frozenset()),
    )


def _class_fit(
    item: CatalogItem,
    main_categories: frozenset[str],
    second_categories: frozenset[str],
    main_class_share: float,
) -> float:
    """Return how well an item's stats suit a champion's classes.

    Args:
        item: The item.
        main_categories: The categories that suit the main class.
        second_categories: Those that suit the second; empty when it has one class.
        main_class_share: How far the main class outweighs the second.

    Returns:
        From 0 to 1.
    """
    stat_categories = STAT_CATEGORIES.intersection(item.categories)
    if not stat_categories:
        return 0.0
    main_fit = len(stat_categories & main_categories) / len(stat_categories)
    if not second_categories:
        return main_fit
    second_fit = len(stat_categories & second_categories) / len(stat_categories)
    return main_class_share * main_fit + (1 - main_class_share) * second_fit


def _affordable_at(gold: GoldEstimate, remaining_gold: float, game_time_seconds: float) -> float:
    """Return when a player will hold some gold, at their income so far.

    Args:
        gold: Their gold.
        remaining_gold: The gold.
        game_time_seconds: The game's clock.

    Returns:
        The game time; now when they hold it already.
    """
    missing_gold = remaining_gold - gold.unspent_gold
    if missing_gold <= 0:
        return game_time_seconds
    earning_seconds = max(game_time_seconds - INCOME_STARTS_AT_SECONDS, SHORTEST_INCOME_SECONDS)
    income_per_second = max(gold.total_gold - GOLD_RULES.starting_gold, 1.0) / earning_seconds
    return game_time_seconds + missing_gold / income_per_second
