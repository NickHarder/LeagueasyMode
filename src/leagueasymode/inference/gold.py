"""Hidden gold (estimator 3): what each player earned and holds; the game shows yours only.

The game gives the gold of the player on this machine (`activePlayer.currentGold`) and nobody
else's. Everyone else's is estimated in two parts.

- **An income model**, from what the game does show: the starting gold, passive gold by the clock,
  gold for each creep at the rate of when it died, kill and assist gold with the bounties the feed
  implies, turret, inhibitor and Baron gold, and the support item's quest gold. Its numbers are
  this season's, from the patch notes (`GoldRules`); those no source confirmed are marked, and the
  scoring harness checks every one against the timelines of recorded games.
- **A filter** (`GoldTracker`) that corrects the model with what the inventory proves. Total gold
  is a normal estimate with a spread, carried forward by the model's income and widened by how
  unsure each kind of income is. Nobody owns more than they earned, so the inventory's worth, with
  what was drunk, placed or lost on a sale, is a floor. A shopping trip that ends leaves little in
  hand, so its end is a measurement, total gold about the inventory's worth plus a small
  leftover, which is weighed against the model's estimate as a Kalman filter weighs one. A support
  item that reaches the next stage of its quest pins the quest's gold at that moment.

The model is tuned live on your own exact gold. Gold per creep is the same for every laner, and
for every jungler, and is the model's least sure number: the gold your own creeps must have paid,
everything else counted, corrects it for every player of your kind.
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from statistics import NormalDist
from typing import Final, Literal

from leagueasymode.game_state import GameEvent, GameSnapshot, ScoreboardItem, ScoreboardPlayer
from leagueasymode.inference.objectives import (
    BARON_KILL_EVENT,
    INHIBITOR_KILLED_EVENT,
    INHIBITOR_NAME_PATTERN,
    TEAM_BY_NUMBER,
)
from leagueasymode.overlay_state import GoldEstimate, PlayerCard, TeamGold
from leagueasymode.patch_data import CONSUMABLE_CATEGORY, ItemCatalog

# A player by team and champion alias, lower-cased, as the players' records are keyed.
type PlayerKey = tuple[str, str]
type CreepKind = Literal["lane", "jungle"]
# Gold per second, each rate from its game time in seconds until the next one's.
type GoldRates = tuple[tuple[float, float], ...]

CHAMPION_KILL_EVENT: Final = "ChampionKill"
TURRET_KILLED_EVENT: Final = "TurretKilled"
SMITE_SPELL_ID: Final = "SummonerSmite"
OTHER_TEAM: Final = {"ORDER": "CHAOS", "CHAOS": "ORDER"}
# "Turret_T1_L_03_A": the turret's team (1 for ORDER), its lane, and its place in the lane counted
# from the base. As open-source readers of the game's API name them; a recording confirms it.
TURRET_NAME_PATTERN: Final = re.compile(
    r"^Turret_T(?P<team>[12])_(?P<lane>[LCR])_(?P<place>\d{2})_A$"
)
TURRET_TIER_BY_LANE_AND_PLACE: Final[Mapping[tuple[str, int], str]] = {
    ("L", 3): "outer",
    ("C", 5): "outer",
    ("R", 3): "outer",
    ("L", 2): "inner",
    ("C", 4): "inner",
    ("R", 2): "inner",
    ("L", 1): "inhibitor",
    ("C", 3): "inhibitor",
    ("R", 1): "inhibitor",
    ("C", 2): "nexus",
    ("C", 1): "nexus",
}
# The support item's quest: World Atlas, Runic Compass, then Bounty of Worlds and the item it
# becomes, by their ids of the 2024 season. An item built from Bounty of Worlds is the last stage
# too, so that a new support item is known by its recipe.
WORLD_ATLAS_ID: Final = 3865
BOUNTY_OF_WORLDS_ID: Final = 3867
SUPPORT_QUEST_STAGE_BY_ITEM_ID: Final[Mapping[int, int]] = {
    3865: 1,
    3866: 2,
    3867: 3,
    3869: 3,
    3870: 3,
    3871: 3,
    3876: 3,
    3877: 3,
}
SECOND_SUPPORT_QUEST_STAGE: Final = 2
LAST_SUPPORT_QUEST_STAGE: Final = 3
# A band holds the truth about 4 times in 5: this many standard deviations each side.
BAND_STANDARD_DEVIATIONS: Final = NormalDist().inv_cdf(0.9)
# A game time this much earlier than the last one seen is a new game's.
NEW_GAME_SLACK_SECONDS: Final = 5.0


@dataclass(frozen=True)
class GoldRules:
    """The season's gold numbers, and how unsure the model is of each kind of income.

    From the patch notes: patch 26.16's passive gold and minion gold, patch 25.9's bounties by
    level. Those no source confirmed are marked "unconfirmed"; recordings check every one.
    """

    starting_gold: float = 500.0
    # 10.5 gold per 5 seconds from 1:30, 11.5 from 15:00, 13 from 25:00.
    passive_gold_rates: GoldRates = ((90.0, 2.1), (900.0, 2.3), (1500.0, 2.6))
    # A lane creep's average gold: 3 melee (19) and 3 ranged (14) a wave, and a cannon (50, and 1
    # more every 90 seconds) every third wave, every second from 15:00, every wave from 25:00.
    lane_gold_per_creep: GoldRates = ((0.0, 18.5), (900.0, 20.1), (1500.0, 23.9))
    # Unconfirmed: what the jungle's camps pay for each point of creep score they give.
    jungle_gold_per_creep: GoldRates = ((0.0, 22.0),)
    # A kill pays 300 up to level 6, then 10 more a level, to 420 at 18.
    base_bounty_gold: float = 300.0
    base_bounty_last_flat_level: int = 6
    base_bounty_gold_per_level: float = 10.0
    # A bounty of 1 gold for every 3 earned from kills and assists since the last death, less the
    # first 100. Unconfirmed: its cap.
    bounty_gold_per_gold_earned: float = 1 / 3
    unapplied_bounty_gold: float = 100.0
    max_bounty_gold: float = 700.0
    # The assisters share half the base bounty; none of the bounty above it.
    assist_share: float = 0.5
    # Unconfirmed, from the wiki: (tier, gold to each of the destroying team, gold shared by the
    # champions that took it).
    turret_gold: tuple[tuple[str, float, float], ...] = (
        ("outer", 50.0, 250.0),
        ("inner", 25.0, 425.0),
        ("inhibitor", 25.0, 375.0),
        ("nexus", 0.0, 50.0),
    )
    # Unconfirmed: gold shared by the champions that take an inhibitor, and Baron's gold to each
    # of the team that kills it.
    inhibitor_gold: float = 50.0
    baron_gold: float = 300.0
    # Unconfirmed: the gold each of the quest's first two stages takes (sources give 400 or 500,
    # and 800 or 1000), how fast a support earns it, what the finished item pays, and what each
    # stage is worth when the catalog does not say what World Atlas cost.
    support_quest_stage_gold: tuple[float, float] = (400.0, 800.0)
    support_quest_starts_at_seconds: float = 90.0
    support_quest_gold_per_second: float = 0.75
    support_item_gold_per_second: float = 0.5
    support_quest_item_gold: float = 400.0
    # After a shopping trip, the gold left in hand: about even from 0 to 600.
    leftover_mean_gold: float = 300.0
    leftover_standard_deviation_gold: float = 175.0
    # A shopping trip buys at least this much, and ends when nothing more is bought for this long.
    shopping_trip_min_gold: float = 300.0
    shopping_trip_end_seconds: float = 5.0
    # A sale gives back 70% of the price.
    sale_loss_share: float = 0.3
    # How unsure each kind of income is, as a share of it, and the income the model does not see
    # (turret plates among it), in gold per second from 1:30.
    creep_gold_uncertainty: float = 0.12
    champion_gold_uncertainty: float = 0.25
    objective_gold_uncertainty: float = 0.3
    quest_gold_uncertainty: float = 0.3
    unseen_gold_per_second: float = 0.15
    unseen_gold_starts_at_seconds: float = 90.0
    # Your own creep gold weighs 1 against the model's 1 for each this much of it, and the tuning
    # stays within these bounds.
    tuning_gold_per_weight: float = 1000.0
    tuning_bounds: tuple[float, float] = (0.75, 1.33)


GOLD_RULES: Final = GoldRules()


@dataclass(frozen=True)
class FeedGold:
    """What a player earned from the feed: kills and assists, and objectives."""

    champion_gold: float = 0.0
    objective_gold: float = 0.0


NO_FEED_GOLD: Final = FeedGold()


@dataclass(frozen=True)
class Income:
    """What a player has earned, by kind, besides the starting gold; creep gold untuned."""

    passive_gold: float = 0.0
    creep_gold: float = 0.0
    champion_gold: float = 0.0
    objective_gold: float = 0.0
    quest_gold: float = 0.0


@dataclass(frozen=True)
class _Anchor:
    """The last moment a player's total gold was estimated afresh, and their income then."""

    game_time_seconds: float
    mean_gold: float
    variance: float
    income: Income


@dataclass
class _PlayerGold:
    """What the tracker remembers of one player between answers."""

    anchor: _Anchor
    inventory: Counter[int]
    items_by_id: dict[int, ScoreboardItem]
    inventory_worth: float
    quest_stage: int
    observed_at_seconds: float = 0.0
    creep_score: int = 0
    creep_gold: float = 0.0
    # What was bought and is no longer owned: drunk, placed, or lost on a sale.
    spent_beyond_inventory_gold: float = 0.0
    # The inventory's worth before the shopping trip under way, if one is.
    shopping_trip_start_worth: float | None = None
    last_purchase_seconds: float = 0.0
    # The game time and quest gold of the last quest stage seen reached.
    quest_pin: tuple[float, float] | None = None
    creep_kind: CreepKind = "lane"


def passive_gold(game_time_seconds: float, rules: GoldRules = GOLD_RULES) -> float:
    """Return the passive gold every player has earned by a moment of the game.

    Args:
        game_time_seconds: The moment.
        rules: The gold numbers.

    Returns:
        The gold.
    """
    return _gold_until(rules.passive_gold_rates, game_time_seconds)


def gold_per_creep(
    creep_kind: CreepKind, game_time_seconds: float, rules: GoldRules = GOLD_RULES
) -> float:
    """Return what one point of creep score pays at a moment of the game, untuned.

    Args:
        creep_kind: "lane" for lane creeps, "jungle" for the jungle's camps.
        game_time_seconds: The moment.
        rules: The gold numbers.

    Returns:
        The gold.
    """
    rates = rules.jungle_gold_per_creep if creep_kind == "jungle" else rules.lane_gold_per_creep
    return next((rate for start, rate in reversed(rates) if game_time_seconds >= start), 0.0)


def base_bounty_gold(level: int, rules: GoldRules = GOLD_RULES) -> float:
    """Return what killing a champion of a level pays, before any bounty.

    Args:
        level: The champion's level.
        rules: The gold numbers.

    Returns:
        The gold.
    """
    levels_above_flat = max(0, level - rules.base_bounty_last_flat_level)
    return rules.base_bounty_gold + rules.base_bounty_gold_per_level * levels_above_flat


def player_key(player: ScoreboardPlayer) -> PlayerKey:
    """Return the key a player is known by: their team and champion alias, lower-cased.

    Args:
        player: The player.

    Returns:
        The key.
    """
    return (player.team, player.champion_alias().lower())


def creep_kind_of(player: ScoreboardPlayer) -> CreepKind:
    """Return which creeps pay a player: the jungle's for one with Smite, the lane's otherwise.

    Args:
        player: The player.

    Returns:
        "jungle" or "lane".
    """
    spells = player.summoner_spells
    has_smite = SMITE_SPELL_ID in {spells.first.spell_id(), spells.second.spell_id()}
    return "jungle" if has_smite else "lane"


def feed_gold(snapshot: GameSnapshot, rules: GoldRules = GOLD_RULES) -> dict[PlayerKey, FeedGold]:
    """Return what each player earned from the feed: kills and assists, and objectives.

    A kill pays the base bounty of the victim's level now, which the victim had or passed when they
    died, and the bounty they had built from kills and assists since their last death.

    Args:
        snapshot: The game's state.
        rules: The gold numbers.

    Returns:
        The gold by player; a player who earned none from the feed is left out.
    """
    champion_gold: defaultdict[PlayerKey, float] = defaultdict(float)
    objective_gold: defaultdict[PlayerKey, float] = defaultdict(float)
    earned_since_death: defaultdict[PlayerKey, float] = defaultdict(float)
    for event in snapshot.event_list.events:
        if event.event_name == CHAMPION_KILL_EVENT:
            victim = _player_named(snapshot, event.victim_name)
            if victim is None:
                continue
            for key, gold in _kill_payments(event, snapshot, victim, earned_since_death, rules):
                champion_gold[key] += gold
                earned_since_death[key] += gold
            earned_since_death[player_key(victim)] = 0.0
        else:
            for key, gold in _objective_payments(event, snapshot, rules):
                objective_gold[key] += gold
    return {
        key: FeedGold(champion_gold=champion_gold[key], objective_gold=objective_gold[key])
        for key in champion_gold.keys() | objective_gold.keys()
    }


def inventory_worth(
    items: Iterable[ScoreboardItem], item_catalog: ItemCatalog | None, rules: GoldRules = GOLD_RULES
) -> float:
    """Return what an inventory cost, each stage of the support item at World Atlas's price.

    Args:
        items: The inventory.
        item_catalog: The patch's items; None while unknown, when the scoreboard's prices are used.
        rules: The gold numbers.

    Returns:
        The gold.
    """
    return sum(_item_price(item, item_catalog, rules) * item.count for item in items)


def support_quest_stage(items: Iterable[ScoreboardItem], item_catalog: ItemCatalog | None) -> int:
    """Return how far the support item in an inventory is in its quest.

    Args:
        items: The inventory.
        item_catalog: The patch's items; None while unknown.

    Returns:
        1 for World Atlas, 2 for Runic Compass, 3 once the quest is done; 0 without the item.
    """
    return max((_support_quest_stage_of(item.item_id, item_catalog) for item in items), default=0)


def chance_of_affording(estimate: GoldEstimate, cost_gold: float) -> float:
    """Return the chance that a player holds at least some gold unspent.

    Args:
        estimate: The player's gold.
        cost_gold: The gold, such as the rest of an item's price.

    Returns:
        The chance, from 0 to 1; 0 or 1 when the gold is exact.
    """
    if estimate.band_gold <= 0:
        return 1.0 if estimate.unspent_gold >= cost_gold else 0.0
    standard_deviation_gold = estimate.band_gold / BAND_STANDARD_DEVIATIONS
    return 1.0 - NormalDist(estimate.unspent_gold, standard_deviation_gold).cdf(cost_gold)


def team_gold(cards: list[PlayerCard]) -> TeamGold | None:
    """Return what each team has earned, or None while any player's gold is unknown.

    Args:
        cards: Every player's card.

    Returns:
        Each team's total gold, and the band of the lead: the players' bands in quadrature.
    """
    known_golds = [(card.side, card.gold) for card in cards if card.gold is not None]
    if not cards or len(known_golds) != len(cards):
        return None
    return TeamGold(
        ally_total_gold=sum(gold.total_gold for side, gold in known_golds if side == "ally"),
        enemy_total_gold=sum(gold.total_gold for side, gold in known_golds if side == "enemy"),
        lead_band_gold=round(math.sqrt(sum(gold.band_gold**2 for _, gold in known_golds))),
    )


class GoldTracker:
    """Follows every player's gold through a game, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self, rules: GoldRules = GOLD_RULES) -> None:
        """Start with no game.

        Args:
            rules: The gold numbers.
        """
        self.rules: Final = rules
        self._players: Final[dict[PlayerKey, _PlayerGold]] = {}
        self._creep_tuning: Final[dict[CreepKind, float]] = {"lane": 1.0, "jungle": 1.0}
        self._last_game_time_seconds = 0.0

    def creep_tuning(self, creep_kind: CreepKind) -> float:
        """Return the factor your own gold has set on one kind of creep gold.

        Args:
            creep_kind: "lane" or "jungle".

        Returns:
            The factor; 1 until your own creeps say otherwise.
        """
        return self._creep_tuning[creep_kind]

    def update(
        self, snapshot: GameSnapshot, item_catalog: ItemCatalog | None
    ) -> dict[PlayerKey, GoldEstimate]:
        """Take in one answer of the game's API, and return every player's gold.

        Args:
            snapshot: The game's state.
            item_catalog: The patch's items, for prices and recipes; None while unknown.

        Returns:
            Each player's gold, by key; the player on this machine's is exact.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._players.clear()
            self._creep_tuning.update({"lane": 1.0, "jungle": 1.0})
        self._last_game_time_seconds = game_time_seconds
        gold_from_feed = feed_gold(snapshot, self.rules)
        incomes: dict[PlayerKey, Income] = {}
        for player in snapshot.players:
            key = player_key(player)
            incomes[key] = self._observe(
                player, game_time_seconds, gold_from_feed.get(key, NO_FEED_GOLD), item_catalog
            )
        own_key = next(
            (
                player_key(player)
                for player in snapshot.players
                if snapshot.is_active_player(player)
            ),
            None,
        )
        if own_key is not None and snapshot.active_player is not None:
            self._take_exact_gold(
                own_key, incomes[own_key], snapshot.active_player.current_gold, game_time_seconds
            )
        return {
            key: self._estimate(
                self._players[key], income, game_time_seconds, is_exact=key == own_key
            )
            for key, income in incomes.items()
        }

    def _observe(
        self,
        player: ScoreboardPlayer,
        game_time_seconds: float,
        gold_from_feed: FeedGold,
        item_catalog: ItemCatalog | None,
    ) -> Income:
        """Take in what the scoreboard shows of one player, and return their income.

        Args:
            player: The player.
            game_time_seconds: The game's clock.
            gold_from_feed: What they earned from the feed.
            item_catalog: The patch's items; None while unknown.

        Returns:
            Their income so far.
        """
        inventory = _inventory_counts(player.items)
        worth = inventory_worth(player.items, item_catalog, self.rules)
        stage = support_quest_stage(player.items, item_catalog)
        state = self._players.setdefault(
            player_key(player),
            _PlayerGold(
                anchor=_Anchor(0.0, self.rules.starting_gold, 0.0, Income()),
                inventory=inventory,
                items_by_id={item.item_id: item for item in player.items},
                inventory_worth=worth,
                quest_stage=stage,
            ),
        )
        state.creep_kind = creep_kind_of(player)
        self._count_creeps(state, player.scores.creep_score, game_time_seconds)
        self._follow_the_inventory(
            state,
            player,
            inventory=inventory,
            worth=worth,
            game_time_seconds=game_time_seconds,
            item_catalog=item_catalog,
        )
        if state.quest_stage >= 1 and stage > state.quest_stage:
            state.quest_pin = (game_time_seconds, self._quest_gold_to_reach(stage))
        state.quest_stage = stage
        state.observed_at_seconds = game_time_seconds
        return Income(
            passive_gold=passive_gold(game_time_seconds, self.rules),
            creep_gold=state.creep_gold,
            champion_gold=gold_from_feed.champion_gold,
            objective_gold=gold_from_feed.objective_gold,
            quest_gold=self._quest_gold(state, game_time_seconds),
        )

    def _count_creeps(self, state: _PlayerGold, creep_score: int, game_time_seconds: float) -> None:
        """Add the creeps killed since the last answer, at the rate halfway between the two.

        Args:
            state: The player's state.
            creep_score: Their creep score now.
            game_time_seconds: The game's clock.
        """
        new_creep_count = creep_score - state.creep_score
        if new_creep_count <= 0:
            return
        halfway_seconds = (state.observed_at_seconds + game_time_seconds) / 2
        state.creep_gold += new_creep_count * gold_per_creep(
            state.creep_kind, halfway_seconds, self.rules
        )
        state.creep_score = creep_score

    def _follow_the_inventory(
        self,
        state: _PlayerGold,
        player: ScoreboardPlayer,
        *,
        inventory: Counter[int],
        worth: float,
        game_time_seconds: float,
        item_catalog: ItemCatalog | None,
    ) -> None:
        """Count what left the inventory since the last answer, and follow a shopping trip.

        Args:
            state: The player's state.
            player: The player.
            inventory: Their inventory's counts by item id now.
            worth: What their inventory cost.
            game_time_seconds: The game's clock.
            item_catalog: The patch's items; None while unknown.
        """
        vanished = state.inventory - inventory
        is_anything_new = bool(inventory - state.inventory)
        state.spent_beyond_inventory_gold += sum(
            self._cost_of_losing(state.items_by_id[item_id], item_catalog, is_anything_new) * count
            for item_id, count in vanished.items()
            if item_id in state.items_by_id
        )
        if worth > state.inventory_worth:
            if state.shopping_trip_start_worth is None:
                state.shopping_trip_start_worth = state.inventory_worth
            state.last_purchase_seconds = game_time_seconds
        state.inventory = inventory
        state.items_by_id = {item.item_id: item for item in player.items}
        state.inventory_worth = worth

    def _cost_of_losing(
        self, item: ScoreboardItem, item_catalog: ItemCatalog | None, is_anything_new: bool
    ) -> float:
        """Return what an item that left the inventory cost beyond its worth there.

        Args:
            item: The item.
            item_catalog: The patch's items; None while unknown.
            is_anything_new: Whether another item came at the same time, which it went into.

        Returns:
            Its whole price when used up; nothing when it went into a new item; the share a sale
            does not give back otherwise.
        """
        price = _item_price(item, item_catalog, self.rules)
        if _is_consumable(item, item_catalog):
            return price
        if is_anything_new:
            return 0.0
        return self.rules.sale_loss_share * price

    def _quest_gold_to_reach(self, stage: int) -> float:
        """Return the quest gold a support item has earned when it reaches a stage.

        Args:
            stage: The stage, 2 or more.

        Returns:
            The gold.
        """
        first_stage_gold, second_stage_gold = self.rules.support_quest_stage_gold
        if stage == SECOND_SUPPORT_QUEST_STAGE:
            return first_stage_gold
        return first_stage_gold + second_stage_gold

    def _quest_gold(self, state: _PlayerGold, game_time_seconds: float) -> float:
        """Return what a player's support item has earned, within its stage's thresholds.

        Args:
            state: The player's state.
            game_time_seconds: The game's clock.

        Returns:
            The gold; 0 without the item.
        """
        rules = self.rules
        first_stage_gold, second_stage_gold = rules.support_quest_stage_gold
        whole_quest_gold = first_stage_gold + second_stage_gold
        pin = state.quest_pin
        if state.quest_stage == 0:
            return 0.0
        if state.quest_stage >= LAST_SUPPORT_QUEST_STAGE:
            done_at_seconds = (
                pin[0]
                if pin is not None and pin[1] >= whole_quest_gold
                else rules.support_quest_starts_at_seconds
                + whole_quest_gold / rules.support_quest_gold_per_second
            )
            return whole_quest_gold + rules.support_item_gold_per_second * max(
                0.0, game_time_seconds - done_at_seconds
            )
        quest_seconds = max(0.0, game_time_seconds - rules.support_quest_starts_at_seconds)
        pinned_seconds = pin[0] - rules.support_quest_starts_at_seconds if pin is not None else 0.0
        rate = (
            pin[1] / pinned_seconds
            if pin is not None and pinned_seconds > 0
            else rules.support_quest_gold_per_second
        )
        stage_floor, stage_ceiling = (
            (0.0, first_stage_gold)
            if state.quest_stage == 1
            else (first_stage_gold, whole_quest_gold)
        )
        return min(max(rate * quest_seconds, stage_floor), stage_ceiling)

    def _take_exact_gold(
        self, key: PlayerKey, income: Income, current_gold: float, game_time_seconds: float
    ) -> None:
        """Pin the player on this machine to their exact gold, and tune creep gold by it.

        Args:
            key: Their key.
            income: Their modelled income.
            current_gold: Their gold in hand, as the game gives it.
            game_time_seconds: The game's clock.
        """
        state = self._players[key]
        total_gold = current_gold + state.inventory_worth + state.spent_beyond_inventory_gold
        state.anchor = _Anchor(game_time_seconds, total_gold, 0.0, income)
        if income.creep_gold <= 0:
            return
        other_gold = (
            self.rules.starting_gold
            + income.passive_gold
            + income.champion_gold
            + income.objective_gold
            + income.quest_gold
        )
        observed_ratio = (total_gold - other_gold) / income.creep_gold
        weight = income.creep_gold / self.rules.tuning_gold_per_weight
        lowest_tuning, highest_tuning = self.rules.tuning_bounds
        tuning = (1.0 + weight * observed_ratio) / (1.0 + weight)
        self._creep_tuning[state.creep_kind] = min(max(tuning, lowest_tuning), highest_tuning)

    def _estimate(
        self, state: _PlayerGold, income: Income, game_time_seconds: float, *, is_exact: bool
    ) -> GoldEstimate:
        """Return a player's gold, after the measurements this answer brings.

        Args:
            state: The player's state.
            income: Their income so far.
            game_time_seconds: The game's clock.
            is_exact: Whether the player is the one on this machine, pinned to their exact gold.

        Returns:
            Their gold.
        """
        owned_gold = state.inventory_worth + state.spent_beyond_inventory_gold
        if is_exact:
            return GoldEstimate(
                source="exact",
                total_gold=round(state.anchor.mean_gold),
                unspent_gold=round(state.anchor.mean_gold - owned_gold),
                band_gold=0,
            )
        modelled_mean, modelled_variance = self._carried_forward(state, income, game_time_seconds)
        measured_mean, measured_variance = self._after_a_shopping_trip(
            state, modelled_mean, modelled_variance, game_time_seconds
        )
        floored_mean = max(measured_mean, owned_gold)
        if (floored_mean, measured_variance) != (modelled_mean, modelled_variance):
            state.anchor = _Anchor(game_time_seconds, floored_mean, measured_variance, income)
        return GoldEstimate(
            source="estimate",
            total_gold=round(floored_mean),
            unspent_gold=round(floored_mean - owned_gold),
            band_gold=round(BAND_STANDARD_DEVIATIONS * math.sqrt(measured_variance)),
        )

    def _carried_forward(
        self, state: _PlayerGold, income: Income, game_time_seconds: float
    ) -> tuple[float, float]:
        """Return the anchor's estimate carried forward by the income since, and its variance.

        Args:
            state: The player's state.
            income: Their income so far.
            game_time_seconds: The game's clock.

        Returns:
            The mean and variance of their total gold.
        """
        rules = self.rules
        anchor = state.anchor
        tuning = self._creep_tuning[state.creep_kind]
        creep_gold = tuning * (income.creep_gold - anchor.income.creep_gold)
        champion_gold = income.champion_gold - anchor.income.champion_gold
        objective_gold = income.objective_gold - anchor.income.objective_gold
        quest_gold = income.quest_gold - anchor.income.quest_gold
        passive_gold_since = income.passive_gold - anchor.income.passive_gold
        unseen_seconds = max(0.0, game_time_seconds - rules.unseen_gold_starts_at_seconds) - max(
            0.0, anchor.game_time_seconds - rules.unseen_gold_starts_at_seconds
        )
        mean_gold = (
            anchor.mean_gold
            + passive_gold_since
            + creep_gold
            + champion_gold
            + objective_gold
            + quest_gold
        )
        variance = (
            anchor.variance
            + (rules.creep_gold_uncertainty * creep_gold) ** 2
            + (rules.champion_gold_uncertainty * champion_gold) ** 2
            + (rules.objective_gold_uncertainty * objective_gold) ** 2
            + (rules.quest_gold_uncertainty * quest_gold) ** 2
            + (rules.unseen_gold_per_second * unseen_seconds) ** 2
        )
        return mean_gold, variance

    def _after_a_shopping_trip(
        self, state: _PlayerGold, mean_gold: float, variance: float, game_time_seconds: float
    ) -> tuple[float, float]:
        """Weigh the end of a shopping trip, if one just ended, against the model's estimate.

        Args:
            state: The player's state.
            mean_gold: The model's estimate of their total gold.
            variance: Its variance.
            game_time_seconds: The game's clock.

        Returns:
            The estimate and its variance after the measurement; unchanged without one.
        """
        rules = self.rules
        trip_start_worth = state.shopping_trip_start_worth
        is_trip_over = (
            trip_start_worth is not None
            and game_time_seconds - state.last_purchase_seconds >= rules.shopping_trip_end_seconds
        )
        if trip_start_worth is None or not is_trip_over:
            return mean_gold, variance
        state.shopping_trip_start_worth = None
        if state.inventory_worth - trip_start_worth < rules.shopping_trip_min_gold:
            return mean_gold, variance
        measured_gold = (
            state.inventory_worth + state.spent_beyond_inventory_gold + rules.leftover_mean_gold
        )
        measurement_variance = rules.leftover_standard_deviation_gold**2
        gain = variance / (variance + measurement_variance)
        return mean_gold + gain * (measured_gold - mean_gold), (1.0 - gain) * variance


def _gold_until(rates: GoldRates, game_time_seconds: float) -> float:
    """Return the gold a schedule of rates has paid by a moment.

    Args:
        rates: Each rate in gold per second, from its game time until the next one's.
        game_time_seconds: The moment.

    Returns:
        The gold.
    """
    ends_seconds = [start for start, _ in rates[1:]] + [math.inf]
    return sum(
        rate * max(0.0, min(game_time_seconds, end_seconds) - start)
        for (start, rate), end_seconds in zip(rates, ends_seconds, strict=True)
    )


def _player_named(snapshot: GameSnapshot, name: str | None) -> ScoreboardPlayer | None:
    """Return the player the feed names, or None for a minion, a turret, a monster or nobody.

    Args:
        snapshot: The game's state.
        name: A name from the feed.

    Returns:
        The player, or None.
    """
    if not name:
        return None
    return next((player for player in snapshot.players if player.is_named(name)), None)


def _kill_payments(
    event: GameEvent,
    snapshot: GameSnapshot,
    victim: ScoreboardPlayer,
    earned_since_death: Mapping[PlayerKey, float],
    rules: GoldRules,
) -> list[tuple[PlayerKey, float]]:
    """Return who a kill paid, and how much.

    Args:
        event: The kill.
        snapshot: The game's state.
        victim: The champion killed.
        earned_since_death: What each player has earned from kills and assists since their last
            death, before this kill.
        rules: The gold numbers.

    Returns:
        The killer's gold, unless a minion, a turret or a monster killed, and each assister's.
    """
    base_gold = base_bounty_gold(victim.level, rules)
    built_bounty_gold = (
        earned_since_death.get(player_key(victim), 0.0) * rules.bounty_gold_per_gold_earned
        - rules.unapplied_bounty_gold
    )
    kill_gold = base_gold + min(max(built_bounty_gold, 0.0), rules.max_bounty_gold)
    killer = _player_named(snapshot, event.killer_name)
    assisters = [
        assister
        for assister in (_player_named(snapshot, name) for name in event.assister_names)
        if assister is not None and assister.team != victim.team
    ]
    killer_payments = (
        [(player_key(killer), kill_gold)]
        if killer is not None and killer.team != victim.team
        else []
    )
    assist_gold = base_gold * rules.assist_share / len(assisters) if assisters else 0.0
    return [*killer_payments, *((player_key(assister), assist_gold) for assister in assisters)]


def _objective_payments(
    event: GameEvent, snapshot: GameSnapshot, rules: GoldRules
) -> list[tuple[PlayerKey, float]]:
    """Return who an objective paid, and how much.

    Args:
        event: An entry of the feed.
        snapshot: The game's state.
        rules: The gold numbers.

    Returns:
        The payments; none for an entry that pays nobody.
    """
    if event.event_name == TURRET_KILLED_EVENT:
        return _turret_payments(event, snapshot, rules)
    if event.event_name == INHIBITOR_KILLED_EVENT:
        inhibitor_match = INHIBITOR_NAME_PATTERN.match(event.inhibitor_killed_name or "")
        if inhibitor_match is None:
            return []
        destroying_team = OTHER_TEAM[TEAM_BY_NUMBER[inhibitor_match["team"]]]
        return _shared_payments(event, snapshot, destroying_team, rules.inhibitor_gold)
    if event.event_name == BARON_KILL_EVENT:
        killer = _player_named(snapshot, event.killer_name)
        return _team_payments(snapshot, killer.team, rules.baron_gold) if killer else []
    return []


def _turret_payments(
    event: GameEvent, snapshot: GameSnapshot, rules: GoldRules
) -> list[tuple[PlayerKey, float]]:
    """Return who a turret paid: its destroyers each, and those who took it a share.

    Args:
        event: The turret's destruction.
        snapshot: The game's state.
        rules: The gold numbers.

    Returns:
        The payments; none for a turret whose name is not understood.
    """
    turret_match = TURRET_NAME_PATTERN.match(event.turret_killed_name or "")
    if turret_match is None:
        return []
    tier = TURRET_TIER_BY_LANE_AND_PLACE.get((turret_match["lane"], int(turret_match["place"])))
    tier_gold = next(
        (
            (team_gold_each, shared_gold)
            for name, team_gold_each, shared_gold in rules.turret_gold
            if name == tier
        ),
        None,
    )
    if tier_gold is None:
        return []
    destroying_team = OTHER_TEAM[TEAM_BY_NUMBER[turret_match["team"]]]
    return [
        *_team_payments(snapshot, destroying_team, tier_gold[0]),
        *_shared_payments(event, snapshot, destroying_team, tier_gold[1]),
    ]


def _team_payments(
    snapshot: GameSnapshot, team: str, gold_each: float
) -> list[tuple[PlayerKey, float]]:
    """Return the same gold to every player of a team.

    Args:
        snapshot: The game's state.
        team: The team.
        gold_each: The gold.

    Returns:
        The payments.
    """
    return [(player_key(player), gold_each) for player in snapshot.players if player.team == team]


def _shared_payments(
    event: GameEvent, snapshot: GameSnapshot, team: str, shared_gold: float
) -> list[tuple[PlayerKey, float]]:
    """Return gold shared by the champions of a team that the feed credits with an objective.

    Args:
        event: The objective's entry: its killer and assisters.
        snapshot: The game's state.
        team: The team that took it.
        shared_gold: The gold.

    Returns:
        The payments; none when no champion of the team is credited.
    """
    credited_names = [event.killer_name, *event.assister_names]
    takers = {
        player_key(player): player
        for player in (_player_named(snapshot, name) for name in credited_names)
        if player is not None and player.team == team
    }
    return [(key, shared_gold / len(takers)) for key in takers]


def _inventory_counts(items: Iterable[ScoreboardItem]) -> Counter[int]:
    """Return how many of each item an inventory holds.

    Args:
        items: The inventory.

    Returns:
        The counts by item id.
    """
    counts: Counter[int] = Counter()
    for item in items:
        counts[item.item_id] += item.count
    return counts


def _support_quest_stage_of(item_id: int, item_catalog: ItemCatalog | None) -> int:
    """Return the quest stage an item is, or 0 for any other item.

    Args:
        item_id: The item.
        item_catalog: The patch's items; None while unknown.

    Returns:
        The stage.
    """
    catalog_item = item_catalog.items_by_id.get(item_id) if item_catalog is not None else None
    if catalog_item is not None and BOUNTY_OF_WORLDS_ID in catalog_item.builds_from:
        return LAST_SUPPORT_QUEST_STAGE
    return SUPPORT_QUEST_STAGE_BY_ITEM_ID.get(item_id, 0)


def _item_price(item: ScoreboardItem, item_catalog: ItemCatalog | None, rules: GoldRules) -> float:
    """Return what one of an item cost: each stage of the support item what World Atlas did.

    Args:
        item: The item.
        item_catalog: The patch's items; None while unknown.
        rules: The gold numbers.

    Returns:
        The gold.
    """
    if _support_quest_stage_of(item.item_id, item_catalog) > 0:
        atlas_price = item_catalog.total_price(WORLD_ATLAS_ID) if item_catalog else None
        return float(atlas_price) if atlas_price is not None else rules.support_quest_item_gold
    catalog_price = item_catalog.total_price(item.item_id) if item_catalog is not None else None
    return float(catalog_price) if catalog_price is not None else float(item.price)


def _is_consumable(item: ScoreboardItem, item_catalog: ItemCatalog | None) -> bool:
    """Return whether an item is used up when used.

    Args:
        item: The item.
        item_catalog: The patch's items; None while unknown.

    Returns:
        Whether it is, by the catalog's categories or else the scoreboard's word.
    """
    catalog_item = item_catalog.items_by_id.get(item.item_id) if item_catalog is not None else None
    if catalog_item is not None:
        return CONSUMABLE_CATEGORY in catalog_item.categories
    return item.is_consumable
