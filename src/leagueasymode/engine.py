"""The engine: ask the game, read its answer, run the estimators, and tell the overlay."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Final

from pydantic import JsonValue, ValidationError

from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_api import GameApiClient
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.backs import BackTracker
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.combat_stats import move_speed_of
from leagueasymode.inference.contests import objective_contests
from leagueasymode.inference.cooldowns import MarkedSpell, marked_cooldown, running_cooldowns
from leagueasymode.inference.experience import ExperienceTracker
from leagueasymode.inference.fights import FIGHT_RULES, FightRules, team_fight
from leagueasymode.inference.gold import GoldTracker, PlayerKey, player_key, team_gold
from leagueasymode.inference.jungle_path import JunglePathTracker
from leagueasymode.inference.objectives import (
    buff_timers,
    dragon_timer,
    inhibitor_timers,
    objective_timers,
)
from leagueasymode.inference.players import numbers_window, player_cards, team_item_gold
from leagueasymode.inference.wards import WardTracker
from leagueasymode.inference.win_chance import (
    WIN_CHANCE_RULES,
    WinChanceRules,
    win_chance,
    win_features,
)
from leagueasymode.inference.you import YouTracker, you_panel
from leagueasymode.league_client import ClientConnector, LeagueClient
from leagueasymode.overlay_state import (
    CooldownTimer,
    MinimapLayout,
    OverlayLayout,
    OverlayPreferences,
    OverlayState,
    PlayerCard,
    PositionEstimate,
)
from leagueasymode.patch_data import GAME_VERSION_PATH, ITEMS_PATH, ItemCatalog, game_version_of
from leagueasymode.player_intel import (
    DEFAULT_PAUSE_SECONDS,
    PlayerRecord,
    PlayerRecords,
    load_player_records,
)
from leagueasymode.refit import ModelWeights

NOT_RUNNING: Final = OverlayState(is_game_running=False)

# Returns the stats of the game's patch, given the game's version (None when unknown).
type PatchStatsLoader = Callable[[str | None], Awaitable[PatchStats | None]]

logger = logging.getLogger(__name__)


def compute_overlay_state(
    payload: JsonValue | None,
    item_catalog: ItemCatalog | None = None,
    *,
    patch_stats: PatchStats | None = None,
    player_records: PlayerRecords | None = None,
    cooldown_timers: list[CooldownTimer] | None = None,
    gold_tracker: GoldTracker | None = None,
    experience_tracker: ExperienceTracker | None = None,
    back_tracker: BackTracker | None = None,
    clue_tracker: ClueTracker | None = None,
    jungle_tracker: JunglePathTracker | None = None,
    ward_tracker: WardTracker | None = None,
    you_tracker: YouTracker | None = None,
    minimap: MinimapLayout | None = None,
    win_rules: WinChanceRules = WIN_CHANCE_RULES,
    fight_rules: FightRules = FIGHT_RULES,
    status: StatusBoard | None = None,
) -> OverlayState:
    """Return what the overlay shows for one answer of the game's API.

    Args:
        payload: The answer, or None when no game answered.
        item_catalog: The patch's items, for the item facts; None while unknown.
        patch_stats: The patch's champion and item stats, for the combat stats; None while
            unknown.
        player_records: Each player's record from the League client, for their intel; None
            while unknown.
        cooldown_timers: The spells marked this game; those not back yet are shown.
        gold_tracker: Follows each player's gold from answer to answer, and takes in this one;
            None to show no gold.
        experience_tracker: The same for each player's experience; None to show none.
        back_tracker: The same for each player's trips to base; None to show none.
        clue_tracker: The same for the clues to where each player is; None to show none.
        jungle_tracker: The same for the junglers' clears; None to show none.
        ward_tracker: The same for the control wards; None to show none.
        you_tracker: The same for how long you have held your gold; None to show no You panel.
        minimap: Where League draws its minimap; None while unknown.
        win_rules: The win chance's weights, hand-set or refit.
        fight_rules: The fight model's, likewise.
        status: Told whether the answer could be read, and what it held; None to tell nothing.

    Returns:
        The overlay's state; no game running when there is no answer or it cannot be read.
    """
    if payload is None:
        return NOT_RUNNING
    try:
        snapshot = GameSnapshot.model_validate(payload)
    except ValidationError as error:
        logger.warning("could not read the game's answer (%d problems)", error.error_count())
        if status is not None:
            status.note_unreadable_answer(error)
        return NOT_RUNNING
    if status is not None:
        status.note_game(snapshot)
    gold_estimates = (
        gold_tracker.update(snapshot, item_catalog) if gold_tracker is not None else None
    )
    level_estimates = (
        experience_tracker.update(snapshot) if experience_tracker is not None else None
    )
    last_backs = (
        back_tracker.update(snapshot, item_catalog, patch_stats)
        if back_tracker is not None
        else None
    )
    position_clues = (
        clue_tracker.update(snapshot, last_backs or {}) if clue_tracker is not None else None
    )
    jungle_paths, camp_timers = (
        jungle_tracker.update(
            snapshot,
            {
                player_key(player): move_speed_of(snapshot, player, patch_stats)
                for player in snapshot.players
            },
        )
        if jungle_tracker is not None
        else ([], [])
    )
    cards = player_cards(
        snapshot,
        item_catalog,
        patch_stats=patch_stats,
        player_records=player_records,
        gold_estimates=gold_estimates,
        level_estimates=level_estimates,
        last_backs=last_backs,
        position_clues=position_clues,
    )
    dragon = dragon_timer(snapshot)
    objectives = objective_timers(snapshot)
    buffs = buff_timers(snapshot)
    inhibitors = inhibitor_timers(snapshot)
    teams_gold = team_gold(cards)
    teams_item_gold = team_item_gold(cards)
    return OverlayState(
        is_game_running=True,
        game_time_seconds=snapshot.game_data.game_time_seconds,
        dragon=dragon,
        objectives=objectives,
        buffs=buffs,
        inhibitors=inhibitors,
        players=cards,
        numbers_window=numbers_window(snapshot),
        team_item_gold=teams_item_gold,
        team_gold=teams_gold,
        cooldowns=running_cooldowns(cooldown_timers or [], snapshot.game_data.game_time_seconds),
        jungle_paths=jungle_paths,
        camp_timers=camp_timers,
        control_wards=(
            ward_tracker.update(snapshot, _locations_by_key(snapshot, cards))
            if ward_tracker is not None
            else []
        ),
        minimap=minimap,
        win_chance=win_chance(
            win_features(
                snapshot,
                team_gold=teams_gold,
                team_item_gold=teams_item_gold,
                dragon=dragon,
                buffs=buffs,
                inhibitors=inhibitors,
            ),
            win_rules,
        ),
        fight=team_fight(snapshot, patch_stats, fight_rules),
        contests=objective_contests(
            snapshot,
            dragon=dragon,
            objectives=objectives,
            position_clues=position_clues or {},
            patch_stats=patch_stats,
        ),
        you=(
            you_panel(
                snapshot,
                holding_gold_seconds=you_tracker.update(snapshot),
                item_catalog=item_catalog,
                patch_stats=patch_stats,
                player_records=player_records,
            )
            if you_tracker is not None
            else None
        ),
    )


def _locations_by_key(
    snapshot: GameSnapshot, cards: list[PlayerCard]
) -> dict[PlayerKey, PositionEstimate]:
    """Return where each living player likely is, by key, from their cards.

    Args:
        snapshot: The game's state.
        cards: Every player's card.

    Returns:
        The positions; a player without one is left out.
    """
    ally_team = snapshot.ally_team()
    location_by_card = {(card.side, card.champion_name): card.location for card in cards}
    locations = {
        player_key(player): location_by_card.get(
            ("ally" if player.team == ally_team else "enemy", player.champion_name)
        )
        for player in snapshot.players
    }
    return {key: location for key, location in locations.items() if location is not None}


class OverlayEngine:
    """Keeps the overlay's state current and passes each new state to its subscribers.

    The state of one answer is worked out on its own (`compute_overlay_state`); the callouts, which
    depend on what changed since the last answer, are added by the engine, which remembers. The
    patch's data is loaded again at each game's start, so a patch that lands between two games is
    picked up without a restart; until it arrives, the last patch's data stands.
    """

    def __init__(
        self,
        game_api: GameApiClient,
        poll_interval_seconds: float,
        connect_to_client: ClientConnector | None = None,
        load_patch_stats: PatchStatsLoader | None = None,
        intel_pause_seconds: float = DEFAULT_PAUSE_SECONDS,
        *,
        minimap_layout: MinimapLayout | None = None,
        model_weights: ModelWeights | None = None,
        preferences: OverlayPreferences | None = None,
        layout: OverlayLayout | None = None,
        status: StatusBoard | None = None,
    ) -> None:
        """Keep the game's API, how often to ask it, and where the patch's data comes from.

        Args:
            game_api: The game's API.
            poll_interval_seconds: How often to ask.
            connect_to_client: Finds the League client, for the patch's item catalog, the game's
                version and each player's record when a game starts; None to go without them.
            load_patch_stats: Returns the stats of the game's patch, for the combat stats; None to
                go without them.
            intel_pause_seconds: The pause after each question about a player.
            minimap_layout: Where League draws its minimap, from its settings; None while
                unknown.
            model_weights: The refit models' weights; None for the hand-set ones.
            preferences: What the player chose to see; None for everything.
            layout: Where the player moved the widgets; None for their usual places.
            status: Told what the engine sees, part by part, for the status page; None for a
                board of its own.
        """
        self.game_api: Final = game_api
        self.poll_interval_seconds: Final = poll_interval_seconds
        self.connect_to_client: Final = connect_to_client
        self.load_patch_stats: Final = load_patch_stats
        self.intel_pause_seconds: Final = intel_pause_seconds
        self.minimap_layout: Final = minimap_layout
        self.model_weights: Final = model_weights or ModelWeights()
        self.status: Final = status or StatusBoard()
        self._item_catalog: ItemCatalog | None = None
        self._patch_stats: PatchStats | None = None
        self._player_records: PlayerRecords | None = None
        # Every player looked up so far, by PUUID, so that none is asked about twice.
        self._record_cache: Final[dict[str, PlayerRecord]] = {}
        self._game_data_task: asyncio.Task[None] | None = None
        # The last answer of the game, which a mark is read against.
        self._last_payload: JsonValue | None = None
        self._cooldown_timers: list[CooldownTimer] = []
        # Each starts over by itself when a new game's clock begins.
        self._gold_tracker: Final = GoldTracker()
        self._experience_tracker: Final = ExperienceTracker()
        self._back_tracker: Final = BackTracker()
        self._clue_tracker: Final = ClueTracker()
        self._jungle_tracker: Final = JunglePathTracker()
        self._ward_tracker: Final = WardTracker()
        self._you_tracker: Final = YouTracker()
        self._preferences = preferences or OverlayPreferences()
        self._layout = layout or OverlayLayout()
        self._current_state = NOT_RUNNING.model_copy(
            update={"preferences": self._preferences, "layout": self._layout}
        )
        self._callouts: Final = CalloutTracker()
        self._subscribers: Final[set[asyncio.Queue[OverlayState]]] = set()

    @property
    def current_state(self) -> OverlayState:
        """The latest state."""
        return self._current_state

    @property
    def item_catalog(self) -> ItemCatalog | None:
        """The patch's item catalog, once the League client has given it."""
        return self._item_catalog

    @property
    def patch_stats(self) -> PatchStats | None:
        """The patch's champion and item stats, once loaded."""
        return self._patch_stats

    @property
    def preferences(self) -> OverlayPreferences:
        """What the player chose to see."""
        return self._preferences

    def set_preferences(self, preferences: OverlayPreferences) -> None:
        """Take the player's new choices, and send the current state again with them.

        Args:
            preferences: What the player chose to see.
        """
        self._preferences = preferences
        self._current_state = self._current_state.model_copy(update={"preferences": preferences})
        self._publish(self._current_state)

    @property
    def layout(self) -> OverlayLayout:
        """Where the player moved the widgets."""
        return self._layout

    def set_layout(self, layout: OverlayLayout) -> None:
        """Take where the player moved the widgets, and send the current state again with it.

        Args:
            layout: The widgets' places.
        """
        self._layout = layout
        self._current_state = self._current_state.model_copy(update={"layout": layout})
        self._publish(self._current_state)

    def mark_cooldown(self, enemy_slot: int, spell: MarkedSpell) -> CooldownTimer | None:
        """Start the timer of a spell the player marks an enemy as having just used.

        Args:
            enemy_slot: The enemy's place in role order, 1 for top to 5 for support.
            spell: "flash", "summoner" for their other summoner spell, or "ultimate".

        Returns:
            The timer, or None when no game runs, there is no such enemy, or the patch's
            cooldowns are not known yet.
        """
        if self._last_payload is None:
            return None
        try:
            snapshot = GameSnapshot.model_validate(self._last_payload)
        except ValidationError:
            return None
        timer = marked_cooldown(snapshot, enemy_slot, spell, self._patch_stats)
        if timer is not None:
            self._cooldown_timers = [*self._cooldown_timers, timer]
            logger.info("marked %s's %s", timer.champion_name, timer.spell_name)
        return timer

    def subscribe(self) -> asyncio.Queue[OverlayState]:
        """Return a queue that receives each new state; a slow reader gets the latest only.

        Returns:
            The queue. Pass it to `unsubscribe` when done.
        """
        updates: asyncio.Queue[OverlayState] = asyncio.Queue(maxsize=1)
        self._subscribers.add(updates)
        return updates

    def unsubscribe(self, updates: asyncio.Queue[OverlayState]) -> None:
        """Stop sending states to a queue.

        Args:
            updates: A queue from `subscribe`.
        """
        self._subscribers.discard(updates)

    async def run(self, stop_requested: asyncio.Event) -> None:
        """Ask the game and publish the overlay's state until a stop is requested.

        Args:
            stop_requested: Set to stop.
        """
        while not stop_requested.is_set():
            payload = await self.game_api.fetch_all_game_data()
            no_answer = self.game_api.last_no_answer
            if payload is None and no_answer is not None:
                self.status.note_no_answer(no_answer)
            answer_state = compute_overlay_state(
                payload,
                self._item_catalog,
                patch_stats=self._patch_stats,
                player_records=self._player_records,
                cooldown_timers=self._cooldown_timers,
                gold_tracker=self._gold_tracker,
                experience_tracker=self._experience_tracker,
                back_tracker=self._back_tracker,
                clue_tracker=self._clue_tracker,
                jungle_tracker=self._jungle_tracker,
                ward_tracker=self._ward_tracker,
                you_tracker=self._you_tracker,
                minimap=self.minimap_layout,
                win_rules=self.model_weights.win_rules,
                fight_rules=self.model_weights.fight_rules,
                status=self.status,
            )
            self._last_payload = payload if answer_state.is_game_running else None
            if answer_state.is_game_running and not self._current_state.is_game_running:
                self._start_loading_the_games_data()
            new_state = answer_state.model_copy(
                update={
                    "callouts": self._callouts.update(answer_state),
                    "preferences": self._preferences,
                    "layout": self._layout,
                }
            )
            if new_state != self._current_state:
                self._current_state = new_state
                self._publish(new_state)
            try:
                await asyncio.wait_for(stop_requested.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    def _start_loading_the_games_data(self) -> None:
        """Load the patch's data and the players' records in the background, once per game start.

        The last game's players are forgotten at once, so that none of them is shown as one of
        this game's; the patch's data keeps its last value until the new one arrives.
        """
        self._player_records = None
        self._cooldown_timers = []
        is_loading = self._game_data_task is not None and not self._game_data_task.done()
        if is_loading:
            return
        self._game_data_task = asyncio.create_task(self._load_the_games_data())

    async def _load_the_games_data(self) -> None:
        """Ask the client for the items and the game's version, then the stats and the players.

        The patch's stats and the players' records are loaded side by side, so that a slow
        download of the stats does not hold back the players.
        """
        client = await self.connect_to_client() if self.connect_to_client is not None else None
        item_count = await self._load_the_item_catalog(client) if client is not None else None
        game_version = (
            game_version_of(await client.get_json(GAME_VERSION_PATH))
            if client is not None
            else None
        )
        self._note_the_client(client, item_count, game_version)
        await asyncio.gather(
            self._load_the_patch_stats(game_version), self._load_the_player_records(client)
        )

    async def _load_the_patch_stats(self, game_version: str | None) -> None:
        """Load the stats of the game's patch, keeping the last ones when none can be had.

        Args:
            game_version: The game's version, or None when unknown.
        """
        if self.load_patch_stats is None:
            self.status.set_part("patch", "off", "Not loaded in this run")
            return
        patch_stats = await self.load_patch_stats(game_version)
        if patch_stats is None:
            self.status.set_part(
                "patch",
                "problem",
                f"No stats for game version {game_version or 'unknown'}: Data Dragon was not "
                "reached, and none are kept",
            )
            return
        self._patch_stats = patch_stats
        logger.info("loaded patch %s's champion and item stats", patch_stats.version)
        self.status.set_part(
            "patch",
            "ok",
            f"Patch {patch_stats.version}: {len(patch_stats.champions_by_key)} champions, "
            f"{len(patch_stats.items_by_id)} items",
        )

    async def _load_the_player_records(self, client: LeagueClient | None) -> None:
        """Ask the League client about each player in the game.

        Args:
            client: The League client, or None when it is not running.
        """
        if self.connect_to_client is None:
            self.status.set_part("players", "off", "Not looked up in this run")
            return
        if client is None:
            self.status.set_part(
                "players", "problem", "Not looked up: the League client was not found"
            )
            return
        player_records = await load_player_records(
            client, self._record_cache, self.intel_pause_seconds
        )
        self._player_records = player_records
        logger.info("looked up %d players", len(player_records))
        ranked_count = sum(
            1 for game_record in player_records.values() if game_record.record.ranked is not None
        )
        self.status.set_part(
            "players",
            "ok" if player_records else "problem",
            f"Looked up {len(player_records)} players; {ranked_count} with a rank",
        )

    async def _load_the_item_catalog(self, client: LeagueClient) -> int | None:
        """Ask the League client for the item catalog, and keep it when it has items.

        Args:
            client: The League client.

        Returns:
            How many items it has, or None when the client gave none.
        """
        items_payload = await client.get_json(ITEMS_PATH)
        catalog = ItemCatalog.from_client_items(items_payload) if items_payload else None
        if catalog is None or not catalog.items_by_id:
            return None
        self._item_catalog = catalog
        logger.info("loaded the item catalog: %d items", len(catalog.items_by_id))
        return len(catalog.items_by_id)

    def _note_the_client(
        self, client: LeagueClient | None, item_count: int | None, game_version: str | None
    ) -> None:
        """Say whether the League client was found when the game started, and what it gave.

        Args:
            client: The client, or None when it was not found.
            item_count: How many items its catalog has, or None when it gave none.
            game_version: The game's version it gave, or None.
        """
        if self.connect_to_client is None:
            self.status.set_part("client", "off", "Not looked for in this run")
        elif client is None:
            self.status.set_part(
                "client",
                "problem",
                "Not found when the game started: no lockfile, and no LeagueClientUx process",
            )
        elif item_count is None:
            self.status.set_part(
                "client",
                "problem",
                f"Found, but it gave no item catalog (game version {game_version or 'unknown'})",
            )
        else:
            self.status.set_part(
                "client",
                "ok",
                f"Answering: game version {game_version or 'unknown'}, {item_count} items",
            )

    def _publish(self, new_state: OverlayState) -> None:
        """Put a state in every subscriber's queue, replacing one not yet read.

        Args:
            new_state: The state.
        """
        for updates in self._subscribers:
            if updates.full():
                updates.get_nowait()
            updates.put_nowait(new_state)
