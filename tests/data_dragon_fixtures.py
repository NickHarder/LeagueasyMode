"""Riot's Data Dragon files for tests: hand-written, in Data Dragon's shape (see the README)."""

import json
from pathlib import Path
from typing import Final

from aiohttp import web

from leagueasymode.data_dragon import PatchFiles, PatchStats

FIXTURES: Final = Path(__file__).parent / "fixtures" / "data_dragon"
FIXTURE_FILES: Final = PatchFiles(
    champions=(FIXTURES / "championFull.json").read_bytes(),
    items=(FIXTURES / "item.json").read_bytes(),
    summoners=(FIXTURES / "summoner.json").read_bytes(),
)
FIXTURE_VERSIONS: Final = ["16.19.1", "16.18.1", "16.17.1"]


def champions_without_growth() -> bytes:
    """The champions' file as Data Dragon serves it since 16.5.1: no attack damage growth."""
    champions = json.loads(FIXTURE_FILES.champions)
    for champion in champions["data"].values():
        champion["stats"]["attackdamageperlevel"] = 0
    return json.dumps(champions).encode()


def version_numbers(version: str) -> tuple[int, ...]:
    return tuple(int(number) for number in version.split("."))


def fixture_patch_stats() -> PatchStats:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    return stats


def fake_data_dragon(
    requested_paths: list[str], versions: list[str], *, growth_missing_since: str | None = None
) -> web.Application:
    """A stand-in Data Dragon; from `growth_missing_since` on, its champions have no attack
    damage growth, as Riot's have had since 16.5.1."""
    application = web.Application()

    def champions_of(version: str) -> bytes:
        is_missing = growth_missing_since is not None and version_numbers(
            version
        ) >= version_numbers(growth_missing_since)
        return champions_without_growth() if is_missing else FIXTURE_FILES.champions

    async def versions_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path)
        return web.json_response(versions)

    async def file_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path)
        if request.match_info["version"] not in versions:
            return web.Response(status=403)
        version = request.match_info["version"]
        file_bytes = {
            "championFull.json": champions_of(version),
            "champion.json": champions_of(version),
            "item.json": FIXTURE_FILES.items,
            "summoner.json": FIXTURE_FILES.summoners,
        }
        if request.match_info["file_name"] not in file_bytes:
            return web.Response(status=404)
        return web.Response(
            body=file_bytes[request.match_info["file_name"]], content_type="application/json"
        )

    application.router.add_get("/api/versions.json", versions_route)
    application.router.add_get("/cdn/{version}/data/en_US/{file_name}", file_route)
    return application
