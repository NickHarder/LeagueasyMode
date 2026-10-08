"""Each patch's champion and item stats, from Riot's Data Dragon, fetched once a patch and kept.

The League client's game data has no champion base stats, so the combat stats come from Data
Dragon: the files Riot publishes for each patch at `ddragon.leagueoflegends.com`, plain files on a
CDN that need no key and no account. When a game starts the engine asks the League client which
patch the game runs, and reads that patch's stats from disk; only a patch not yet on disk is
fetched, so the internet is reached once a patch, and the requests name only the patch and the
file, nothing about the player. Without Data Dragon, the newest patch on disk stands in.
"""

import logging
import os
import re
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import aiohttp
import truststore
from pydantic import Field, TypeAdapter, ValidationError

from leagueasymode.game_state import RiotPayloadModel

DEFAULT_DATA_DRAGON_BASE_URL: Final = "https://ddragon.leagueoflegends.com"
VERSIONS_PATH: Final = "/api/versions.json"
# championFull.json holds champion.json's base stats and each champion's spells besides.
CHAMPIONS_FILE_NAME: Final = "championFull.json"
ITEMS_FILE_NAME: Final = "item.json"
SUMMONERS_FILE_NAME: Final = "summoner.json"
# How an item's description states its haste: "<attention>20</attention> Ability Haste".
ABILITY_HASTE_PATTERN: Final = re.compile(r"<attention>\s*(\d+)\s*</attention>\s*Ability Haste")
SUMMONER_SPELL_HASTE_PATTERN: Final = re.compile(
    r"<attention>\s*(\d+)\s*</attention>\s*Summoner Spell Haste"
)
ULTIMATE_SPELL_INDEX: Final = 3
DATA_DRAGON_LOCALE: Final = "en_US"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 15.0
# A Data Dragon version, such as "16.19.1". Nothing else may name a directory on disk.
DATA_DRAGON_VERSION_PATTERN: Final = re.compile(
    r"^(?P<major>\d{1,4})\.(?P<minor>\d{1,4})\.\d{1,4}$"
)
# The game's version as the League client gives it, such as "16.19.712.1234": its patch is the
# first two numbers.
GAME_VERSION_PATTERN: Final = re.compile(r"^(?P<major>\d{1,4})\.(?P<minor>\d{1,4})(\.|$)")
# The game's raw name of a champion is this prefix and the champion's id: Data Dragon's own id.
RAW_CHAMPION_NAME_PREFIX: Final = "game_character_displayname_"
VERSIONS_ADAPTER: Final = TypeAdapter[list[str]](list[str])

logger = logging.getLogger(__name__)

type Patch = tuple[int, int]


class ChampionBaseStats(RiotPayloadModel):
    """A champion's stats at level 1, and what each grows by per level."""

    health: float = Field(alias="hp")
    health_per_level: float = Field(alias="hpperlevel")
    armor: float
    armor_per_level: float = Field(alias="armorperlevel")
    magic_resist: float = Field(alias="spellblock")
    magic_resist_per_level: float = Field(alias="spellblockperlevel")
    attack_damage: float = Field(alias="attackdamage")
    attack_damage_per_level: float = Field(alias="attackdamageperlevel")
    attack_speed: float = Field(alias="attackspeed")
    # Bonus attack speed per level, in percent: 2.5 is 2.5%.
    attack_speed_per_level_percent: float = Field(alias="attackspeedperlevel")
    move_speed: float = Field(alias="movespeed")


class DataDragonSpell(RiotPayloadModel):
    """One of a champion's four spells, Q, W, E and R in that order."""

    cooldown: list[float] = Field(default_factory=list)


class DataDragonChampion(RiotPayloadModel):
    """One champion of Data Dragon's `championFull.json`."""

    champion_id: str = Field(alias="id")
    name: str
    stats: ChampionBaseStats
    spells: list[DataDragonSpell] = Field(default_factory=list)


class DataDragonChampions(RiotPayloadModel):
    """Data Dragon's `championFull.json`: every champion by id."""

    data: dict[str, DataDragonChampion]


class DataDragonSummonerSpell(RiotPayloadModel):
    """One summoner spell of Data Dragon's `summoner.json`."""

    spell_id: str = Field(alias="id")
    name: str = ""
    cooldown: list[float] = Field(default_factory=list)


class DataDragonSummonerSpells(RiotPayloadModel):
    """Data Dragon's `summoner.json`: every summoner spell by id ("SummonerFlash")."""

    data: dict[str, DataDragonSummonerSpell]


class ItemStatBonuses(RiotPayloadModel):
    """What one item adds to its holder's stats. Data Dragon leaves out a stat an item lacks."""

    flat_health: float = Field(default=0.0, alias="FlatHPPoolMod")
    flat_armor: float = Field(default=0.0, alias="FlatArmorMod")
    flat_magic_resist: float = Field(default=0.0, alias="FlatSpellBlockMod")
    flat_attack_damage: float = Field(default=0.0, alias="FlatPhysicalDamageMod")
    flat_ability_power: float = Field(default=0.0, alias="FlatMagicDamageMod")
    # Bonus attack speed as a fraction: 0.25 is 25%.
    attack_speed_fraction: float = Field(default=0.0, alias="PercentAttackSpeedMod")
    flat_move_speed: float = Field(default=0.0, alias="FlatMovementSpeedMod")
    # Bonus move speed as a fraction of the flat total.
    move_speed_fraction: float = Field(default=0.0, alias="PercentMovementSpeedMod")


class DataDragonItem(RiotPayloadModel):
    """One item of Data Dragon's `item.json`."""

    name: str = ""
    # The item's text, which states the haste it gives; Data Dragon's stats leave haste out.
    description: str = ""
    stats: ItemStatBonuses = Field(default_factory=ItemStatBonuses)


@dataclass(frozen=True)
class ItemHaste:
    """The haste one item gives: to abilities, and to summoner spells."""

    ability_haste: float
    summoner_spell_haste: float


NO_HASTE: Final = ItemHaste(ability_haste=0.0, summoner_spell_haste=0.0)


@dataclass(frozen=True)
class PatchFiles:
    """One patch's three files from Data Dragon, as they came."""

    champions: bytes
    items: bytes
    summoners: bytes


class DataDragonItems(RiotPayloadModel):
    """Data Dragon's `item.json`: every item by its id, as text."""

    data: dict[str, DataDragonItem]


class PatchStats:
    """One patch's champions (base stats and spells), items and summoner spells."""

    def __init__(
        self,
        version: str,
        champions: list[DataDragonChampion],
        items_by_id: dict[int, DataDragonItem],
        summoner_spells: list[DataDragonSummonerSpell],
    ) -> None:
        """Index the champions by id and by name, both without case.

        Args:
            version: Data Dragon's version of the patch, such as "16.19.1".
            champions: Every champion.
            items_by_id: Every item.
            summoner_spells: Every summoner spell.
        """
        self.version: Final = version
        self.champions_by_key: Final = {
            key.casefold(): champion
            for champion in champions
            for key in (champion.name, champion.champion_id)
        }
        self.items_by_id: Final = items_by_id
        self.summoner_spells_by_id: Final = {spell.spell_id: spell for spell in summoner_spells}

    @classmethod
    def from_data_dragon(cls, version: str, patch_files: PatchFiles) -> "PatchStats | None":
        """Return a patch's stats from Data Dragon's files, or None when they cannot be read.

        Args:
            version: Data Dragon's version of the patch.
            patch_files: `championFull.json`, `item.json` and `summoner.json`.

        Returns:
            The stats; None when any file is not Data Dragon's or there are no champions.
        """
        try:
            champions = DataDragonChampions.model_validate_json(patch_files.champions)
            items = DataDragonItems.model_validate_json(patch_files.items)
            summoner_spells = DataDragonSummonerSpells.model_validate_json(patch_files.summoners)
        except ValidationError as error:
            logger.warning(
                "could not read Data Dragon's files for %s (%d problems)",
                version,
                error.error_count(),
            )
            return None
        if not champions.data:
            return None
        return cls(
            version,
            list(champions.data.values()),
            {int(item_id): item for item_id, item in items.data.items() if item_id.isdecimal()},
            list(summoner_spells.data.values()),
        )

    def champion_base_stats(
        self, raw_champion_name: str, champion_name: str
    ) -> ChampionBaseStats | None:
        """Return a champion's base stats, found by the game's raw name or else by its name.

        The raw name (`game_character_displayname_MonkeyKing`) is the same in every language; the
        name (`Wukong`) is in the game's language, which matches Data Dragon's English names only
        in English.

        Args:
            raw_champion_name: The scoreboard's `rawChampionName`.
            champion_name: The scoreboard's `championName`.

        Returns:
            The base stats, or None for a champion this patch's files do not have.
        """
        champion = self._champion(raw_champion_name, champion_name)
        return champion.stats if champion is not None else None

    def ultimate_cooldowns(
        self, raw_champion_name: str, champion_name: str
    ) -> tuple[float, ...] | None:
        """Return a champion's ultimate's cooldown at each rank, in seconds before haste.

        Args:
            raw_champion_name: The scoreboard's `rawChampionName`.
            champion_name: The scoreboard's `championName`.

        Returns:
            The cooldowns, rank 1 first, or None for a champion the patch's files do not have.
        """
        champion = self._champion(raw_champion_name, champion_name)
        if champion is None or len(champion.spells) <= ULTIMATE_SPELL_INDEX:
            return None
        return tuple(champion.spells[ULTIMATE_SPELL_INDEX].cooldown)

    def summoner_spell_cooldown(self, spell_id: str) -> float | None:
        """Return a summoner spell's cooldown, in seconds before haste.

        Args:
            spell_id: Data Dragon's id of the spell, such as "SummonerFlash".

        Returns:
            The cooldown, or None for a spell the patch's files do not have.
        """
        spell = self.summoner_spells_by_id.get(spell_id)
        return spell.cooldown[0] if spell is not None and spell.cooldown else None

    def item_bonuses(self, item_id: int) -> ItemStatBonuses | None:
        """Return what an item adds to its holder's stats.

        Args:
            item_id: The item.

        Returns:
            The bonuses, or None for an item this patch's files do not have.
        """
        item = self.items_by_id.get(item_id)
        return item.stats if item is not None else None

    def item_haste(self, item_id: int) -> ItemHaste:
        """Return the haste an item gives, as its description states it.

        Args:
            item_id: The item.

        Returns:
            The haste; none for an item the patch's files do not have.
        """
        item = self.items_by_id.get(item_id)
        if item is None:
            return NO_HASTE
        ability_match = ABILITY_HASTE_PATTERN.search(item.description)
        summoner_match = SUMMONER_SPELL_HASTE_PATTERN.search(item.description)
        return ItemHaste(
            ability_haste=float(ability_match.group(1)) if ability_match else 0.0,
            summoner_spell_haste=float(summoner_match.group(1)) if summoner_match else 0.0,
        )

    def _champion(self, raw_champion_name: str, champion_name: str) -> DataDragonChampion | None:
        """Return a champion, found by the game's raw name or else by its name, without case.

        Args:
            raw_champion_name: The scoreboard's `rawChampionName`.
            champion_name: The scoreboard's `championName`.

        Returns:
            The champion, or None when the patch's files do not have it.
        """
        champion_id = raw_champion_name.removeprefix(RAW_CHAMPION_NAME_PREFIX)
        for key in (champion_id, champion_name):
            champion = self.champions_by_key.get(key.casefold()) if key else None
            if champion is not None:
                return champion
        return None


class PatchStatsStore:
    """Data Dragon's files on disk: `<version>/championFull.json`, `item.json`, `summoner.json`."""

    def __init__(self, directory: Path) -> None:
        """Keep where the patches are.

        Args:
            directory: The directory; made when the first patch is saved.
        """
        self.directory: Final = directory

    def cached_versions(self) -> list[str]:
        """Return the versions of the patches on disk, newest first.

        Returns:
            The versions.
        """
        if not self.directory.is_dir():
            return []
        versions = [
            entry.name
            for entry in self.directory.iterdir()
            if entry.is_dir() and DATA_DRAGON_VERSION_PATTERN.match(entry.name)
        ]
        return sorted(versions, key=_version_numbers, reverse=True)

    def load(self, version: str) -> PatchStats | None:
        """Return a patch's stats from disk.

        Args:
            version: The patch's Data Dragon version.

        Returns:
            The stats, or None when the patch is not on disk, a file is missing or cannot be read.
        """
        if not DATA_DRAGON_VERSION_PATTERN.match(version):
            return None
        patch_directory = self.directory / version
        try:
            patch_files = PatchFiles(
                champions=(patch_directory / CHAMPIONS_FILE_NAME).read_bytes(),
                items=(patch_directory / ITEMS_FILE_NAME).read_bytes(),
                summoners=(patch_directory / SUMMONERS_FILE_NAME).read_bytes(),
            )
        except OSError:
            return None
        return PatchStats.from_data_dragon(version, patch_files)

    def save(self, version: str, patch_files: PatchFiles) -> None:
        """Keep a patch's files on disk, each written whole or not at all.

        Args:
            version: The patch's Data Dragon version.
            patch_files: The patch's files.

        Raises:
            ValueError: When the version is not a Data Dragon version.
        """
        if not DATA_DRAGON_VERSION_PATTERN.match(version):
            message = f"not a Data Dragon version: {version!r}"
            raise ValueError(message)
        patch_directory = self.directory / version
        patch_directory.mkdir(parents=True, exist_ok=True)
        for file_name, file_bytes in (
            (CHAMPIONS_FILE_NAME, patch_files.champions),
            (ITEMS_FILE_NAME, patch_files.items),
            (SUMMONERS_FILE_NAME, patch_files.summoners),
        ):
            _write_whole(patch_directory / file_name, file_bytes)


def create_system_tls_context() -> ssl.SSLContext:
    """Return a TLS context that trusts what this machine trusts: the Keychain on a Mac.

    Python's own context may find no certificates on a Mac, depending on how Python was installed;
    the system's trust store always has them.

    Returns:
        The context.
    """
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class DataDragonClient:
    """Asks Data Dragon for its list of patches and for a patch's files."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        tls_context: ssl.SSLContext | None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Keep what every request needs.

        Args:
            session: The HTTP session.
            base_url: Data Dragon's address, or a stand-in's.
            tls_context: The context for HTTPS, which trusts the system's certificates; None for
                a stand-in served over plain HTTP.
            request_timeout_seconds: How long one request may take.
        """
        self.session: Final = session
        self.base_url: Final = base_url.rstrip("/")
        self.tls_context: Final = tls_context
        self.request_timeout: Final = aiohttp.ClientTimeout(total=request_timeout_seconds)

    async def versions(self) -> list[str]:
        """Return Data Dragon's versions, newest first, leaving out any that is not a version.

        Returns:
            The versions; empty when Data Dragon cannot be reached.
        """
        versions_bytes = await self.get_bytes(VERSIONS_PATH)
        if versions_bytes is None:
            return []
        try:
            versions = VERSIONS_ADAPTER.validate_json(versions_bytes)
        except ValidationError:
            logger.warning("Data Dragon's list of versions is not a list of versions")
            return []
        return [version for version in versions if DATA_DRAGON_VERSION_PATTERN.match(version)]

    async def patch_files(self, version: str) -> PatchFiles | None:
        """Return a patch's `championFull.json`, `item.json` and `summoner.json`.

        Args:
            version: The patch's Data Dragon version.

        Returns:
            The files, or None when any cannot be had.
        """
        data_path = f"/cdn/{version}/data/{DATA_DRAGON_LOCALE}"
        champions_bytes = await self.get_bytes(f"{data_path}/{CHAMPIONS_FILE_NAME}")
        if champions_bytes is None:
            return None
        items_bytes = await self.get_bytes(f"{data_path}/{ITEMS_FILE_NAME}")
        if items_bytes is None:
            return None
        summoners_bytes = await self.get_bytes(f"{data_path}/{SUMMONERS_FILE_NAME}")
        if summoners_bytes is None:
            return None
        return PatchFiles(champions=champions_bytes, items=items_bytes, summoners=summoners_bytes)

    async def get_bytes(self, path: str) -> bytes | None:
        """Return one file of Data Dragon.

        Args:
            path: The file's path.

        Returns:
            The file, or None on any error status, a timeout or no connection.
        """
        try:
            async with self.session.get(
                self.base_url + path,
                ssl=self.tls_context if self.tls_context is not None else True,
                timeout=self.request_timeout,
            ) as response:
                if response.status != 200:
                    logger.warning("Data Dragon answered %d for %s", response.status, path)
                    return None
                return await response.read()
        except (aiohttp.ClientError, TimeoutError, ssl.SSLError) as error:
            logger.warning("Data Dragon did not answer %s: %s", path, type(error).__name__)
            return None


async def load_patch_stats(
    client: DataDragonClient | None, store: PatchStatsStore, game_version: str | None
) -> PatchStats | None:
    """Return the stats of the game's patch: from disk when kept, otherwise fetched and then kept.

    The game's patch is the first two numbers of its version. When the game's version is unknown,
    or Data Dragon has not published that patch yet, Data Dragon's newest patch is used. When Data
    Dragon cannot be reached, or downloads are off, the newest patch on disk stands in.

    Args:
        client: Data Dragon; None when downloads are off.
        store: The patches on disk.
        game_version: The game's version from the League client, or None when unknown.

    Returns:
        The stats, or None when no patch can be had at all.
    """
    game_patch = _patch_of_game_version(game_version)
    cached_versions = store.cached_versions()
    cached_match = next(
        (version for version in cached_versions if _patch_of_version(version) == game_patch),
        None,
    )
    cached_stats = store.load(cached_match) if cached_match is not None else None
    if cached_stats is not None:
        return cached_stats
    fetched_stats = await _fetch_and_keep(client, store, game_patch) if client is not None else None
    if fetched_stats is not None:
        return fetched_stats
    for version in cached_versions:
        stand_in_stats = store.load(version)
        if stand_in_stats is not None:
            logger.warning("using patch %s's stats for patch %s", version, game_version)
            return stand_in_stats
    return None


async def _fetch_and_keep(
    client: DataDragonClient, store: PatchStatsStore, game_patch: Patch | None
) -> PatchStats | None:
    """Return a patch's stats from Data Dragon, kept on disk for the next game.

    Args:
        client: Data Dragon.
        store: The patches on disk.
        game_patch: The game's patch, or None for Data Dragon's newest.

    Returns:
        The stats, or None when Data Dragon cannot give them.
    """
    versions = await client.versions()
    version = next(
        (version for version in versions if _patch_of_version(version) == game_patch),
        versions[0] if versions else None,
    )
    if version is None:
        return None
    cached_stats = store.load(version)
    if cached_stats is not None:
        return cached_stats
    patch_files = await client.patch_files(version)
    if patch_files is None:
        return None
    stats = PatchStats.from_data_dragon(version, patch_files)
    if stats is None:
        return None
    store.save(version, patch_files)
    logger.info("fetched and kept patch %s's stats from Data Dragon", version)
    return stats


def _patch_of_game_version(game_version: str | None) -> Patch | None:
    """Return the patch of the game's version, such as (16, 19) for "16.19.712.1234".

    Args:
        game_version: The game's version, or None.

    Returns:
        The patch, or None when the version is unknown or not a version.
    """
    version_match = GAME_VERSION_PATTERN.match(game_version) if game_version else None
    if version_match is None:
        return None
    return int(version_match.group("major")), int(version_match.group("minor"))


def _patch_of_version(version: str) -> Patch | None:
    """Return the patch of a Data Dragon version, such as (16, 19) for "16.19.1".

    Args:
        version: The version.

    Returns:
        The patch, or None when it is not a Data Dragon version.
    """
    version_match = DATA_DRAGON_VERSION_PATTERN.match(version)
    if version_match is None:
        return None
    return int(version_match.group("major")), int(version_match.group("minor"))


def _version_numbers(version: str) -> tuple[int, ...]:
    """Return a version's numbers, for sorting.

    Args:
        version: A Data Dragon version.

    Returns:
        Its numbers.
    """
    return tuple(int(number) for number in version.split("."))


def _write_whole(path: Path, file_bytes: bytes) -> None:
    """Write a file whole: to a temporary file beside it, then moved over it.

    Args:
        path: The file.
        file_bytes: What it holds.
    """
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(file_bytes)
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
