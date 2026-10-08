"""Riot's Data Dragon files for tests: hand-written, in Data Dragon's shape (see the README)."""

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


def fixture_patch_stats() -> PatchStats:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    return stats


def fake_data_dragon(requested_paths: list[str], versions: list[str]) -> web.Application:
    application = web.Application()

    async def versions_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path)
        return web.json_response(versions)

    async def file_route(request: web.Request) -> web.Response:
        requested_paths.append(request.path)
        if request.match_info["version"] not in versions:
            return web.Response(status=403)
        file_bytes = {
            "championFull.json": FIXTURE_FILES.champions,
            "item.json": FIXTURE_FILES.items,
            "summoner.json": FIXTURE_FILES.summoners,
        }
        return web.Response(
            body=file_bytes[request.match_info["file_name"]], content_type="application/json"
        )

    application.router.add_get("/api/versions.json", versions_route)
    application.router.add_get("/cdn/{version}/data/en_US/{file_name}", file_route)
    return application
