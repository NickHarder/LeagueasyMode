"""Problem reports: one click on the Mac sends what is needed to find what went wrong."""

import datetime
import json
import lzma
from pathlib import Path
from typing import Final

import aiohttp

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import OverlayEngine
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.problem_report import (
    REPORTS_FOLDER,
    make_problem_report,
    player_identities,
    scrub,
)
from local_servers import serve, unused_local_url
from test_anonymize import identity_strings, write_source_recording

NOW: Final = datetime.datetime(2026, 10, 28, 21, 40, tzinfo=datetime.UTC)
SHADOW_STEP: Final = DEFAULT_PLAYERS[7]


def test_each_name_the_game_gave_is_known() -> None:
    identities = player_identities(all_game_data(60.0))
    assert SHADOW_STEP.riot_id in identities
    assert SHADOW_STEP.riot_id_game_name in identities
    assert player_identities(None) == set()


def test_names_and_the_home_folder_are_scrubbed(tmp_path: Path) -> None:
    text = (
        f"Traceback in /Users/someone/Library/x.py: {SHADOW_STEP.riot_id} killed "
        f"{SHADOW_STEP.riot_id_game_name}\n"
    )
    scrubbed = scrub(
        text, {SHADOW_STEP.riot_id, SHADOW_STEP.riot_id_game_name}, Path("/Users/someone")
    )
    assert scrubbed == "Traceback in ~/Library/x.py: [player] killed [player]\n"


def test_a_report_holds_the_facts_the_log_and_the_game_so_far_without_a_name(
    tmp_path: Path,
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    game = write_source_recording(tmp_path)
    game.rename(recordings / "game-now.jsonl.xz")
    (recordings / "crash-reports").mkdir()
    (recordings / "crash-reports" / "crash-1.json").write_text("{}")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "engine.1.log").write_text(f"the last run, {SHADOW_STEP.riot_id} in it\nTraceback\n")
    (logs / "engine.log").write_text("".join(f"line {index}\n" for index in range(900)))
    board = StatusBoard(home_directory=tmp_path)
    report_directory = make_problem_report(
        recordings_directory=recordings,
        note=f"keys stopped, {SHADOW_STEP.riot_id_game_name} was there",
        app_facts={"engine": "Engine: running", "keyboard": "Keyboard: handed back once"},
        status_report=board.report(),
        engine_log=logs / "engine.log",
        identities={SHADOW_STEP.riot_id, SHADOW_STEP.riot_id_game_name},
        home_directory=tmp_path,
        now=NOW,
    )
    assert report_directory == recordings / REPORTS_FOLDER / "report-2026-10-28T21-40-00Z"
    names = sorted(path.name for path in report_directory.iterdir())
    assert names == [
        "engine-log.txt",
        "game-so-far.jsonl.xz",
        "previous-engine-log.txt",
        "report.json",
    ]
    report = json.loads((report_directory / "report.json").read_text())
    assert report["note"] == "keys stopped, [player] was there"
    assert report["app_facts"]["keyboard"] == "Keyboard: handed back once"
    assert report["crash_reports"] == ["crash-1.json"]
    # The recordings' folder, as names and sizes: what was recorded, closed and sent shows
    # without asking the owner to look (none of their games had reached the repository).
    assert [(item["name"], item["size_bytes"] > 0) for item in report["recordings"]] == [
        ("game-now.jsonl.xz", True)
    ]
    assert report["status"]["parts"]
    log_text = (report_directory / "engine-log.txt").read_text()
    assert log_text.startswith("line 400\n") and log_text.endswith("line 899\n")
    assert "[player]" in (report_directory / "previous-engine-log.txt").read_text()
    every_text = "\n".join(
        [
            (report_directory / "report.json").read_text(),
            (report_directory / "previous-engine-log.txt").read_text(),
            lzma.decompress((report_directory / "game-so-far.jsonl.xz").read_bytes()).decode(),
        ]
    )
    assert not [identity for identity in identity_strings() if identity in every_text]


async def test_the_app_asks_for_a_report_and_nothing_else_can() -> None:
    asked: list[tuple[str, dict[str, str]]] = []

    async def make_report(note: str, app_facts: dict[str, str]) -> str:
        asked.append((note, app_facts))
        return "report-2026-10-28T21-40-00Z"

    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        async with serve(create_overlay_application(engine, make_report=make_report)) as url:
            body = {"note": "keys stopped", "app": {"engine": "Engine: running"}}
            async with session.post(url + "/report", json=body) as refused:
                refused_status = refused.status
            async with session.post(
                url + "/report", json=body, headers={"X-LeagueasyMode-Request": "report"}
            ) as made:
                made_status = made.status
                made_body = await made.json()
            async with session.post(
                url + "/report",
                json={"note": 5},
                headers={"X-LeagueasyMode-Request": "report"},
            ) as malformed:
                malformed_status = malformed.status
    assert (refused_status, made_status, malformed_status) == (403, 201, 400)
    assert made_body == {"report": "report-2026-10-28T21-40-00Z"}
    assert asked == [("keys stopped", {"engine": "Engine: running"})]
