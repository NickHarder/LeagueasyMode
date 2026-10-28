"""Claude's take (phase 11.8): reworded lines that keep the numbers and names, or the approved line.

These tests never call Claude: a stand-in `claude` command answers with canned text.
"""

import asyncio
import json
import stat
import sys
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from aiohttp import web
from pydantic import ValidationError

from client_game_payloads import details_payload, summary_payload, timeline_payload
from game_payloads import all_game_data, champion_kill_event
from leagueasymode.engine import OverlayEngine
from leagueasymode.friends import FriendsList
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.roast.claude_take import (
    ClaudeTake,
    ClaudeTakeSettings,
    SlottedLine,
    find_claude_command,
    load_claude_take_settings,
    save_claude_take_settings,
    slot_out,
    take_problems,
)
from leagueasymode.roast.client_game import champion_names, read_client_game
from leagueasymode.roast.last_game import LastGameRoast, roast_path_beside
from leagueasymode.roast.moments import load_moment_lines
from leagueasymode.roast.rules import LaneRules
from leagueasymode.roast.safety import moderation_problems
from leagueasymode.roast.team_calls import load_team_call_lines
from leagueasymode.roast.templates import load_templates
from local_servers import serve, unused_local_url

LINE: Final = "gg. TEAM DIFF. Our Lee Sin was 1,661 gold behind Vi at 14:00."
CHAMPIONS: Final = frozenset({"Lee Sin", "Vi", "Ahri"})
PIRATE: Final = "Yarr! {c1} sank {n1} doubloons behind {c2} by {n2}. TEAM DIFF, matey."
PIRATE_SETTINGS: Final = ClaudeTakeSettings(enabled=True, style="pirate")
CLAUDE_HEADERS: Final = {"X-LeagueasyMode-Request": "claude-take"}


def stand_in_claude(tmp_path: Path, answer: str, *, exit_code: int = 0, delay: float = 0.0) -> Path:
    """A `claude` that logs its arguments and question, waits, and answers with canned text."""
    script = tmp_path / "claude"
    log = tmp_path / "claude-log.jsonl"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        f"time.sleep({delay})\n"
        f"with open({str(log)!r}, 'a') as log:\n"
        "    call = {'arguments': sys.argv[1:], 'question': sys.stdin.read()}\n"
        "    log.write(json.dumps(call) + '\\n')\n"
        f"sys.stdout.write({answer!r})\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def echoing_claude(tmp_path: Path, prefix: str) -> Path:
    """A `claude` that answers with the line it was sent, slots and all, after a prefix."""
    script = tmp_path / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "question = sys.stdin.read()\n"
        "line = question.split('Line:', 1)[1].strip()\n"
        f"sys.stdout.write({prefix!r} + line)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def asked(tmp_path: Path) -> list[dict[str, object]]:
    log = tmp_path / "claude-log.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_numbers_and_names_become_slots() -> None:
    slotted = slot_out(LINE, CHAMPIONS)
    assert slotted == SlottedLine(
        template="gg. TEAM DIFF. Our {c1} was {n1} gold behind {c2} at {n2}.",
        values={"c1": "Lee Sin", "c2": "Vi", "n1": "1,661", "n2": "14:00"},
    )


def test_a_good_answer_is_filled_with_the_lines_own_numbers_and_names() -> None:
    take, problems = take_problems(slot_out(LINE, CHAMPIONS), PIRATE, 140)
    assert problems == []
    assert take == "Yarr! Lee Sin sank 1,661 doubloons behind Vi by 14:00. TEAM DIFF, matey."


@pytest.mark.parametrize(
    ("answer", "problem"),
    [
        ("Yarr, {c1} trailed {c2} by {n1} at {n2}, ask Yasuo.", "names something"),
        ("{c1} lost 3 times to {c2}, {n1} at {n2}.", "number outside a slot"),
        ("{c1} trailed {c2} at {n2}.", "each slot exactly once"),
        ("{c1} trailed {c2} by {n1} at {n2} and {n3}.", "each slot exactly once"),
        ("{c1} trailed {c2}\nby {n1} at {n2}.", "not one line"),
        ("{c1} " + "slow " * 40 + "{c2} {n1} {n2}", "longer than 140"),
        ("{c1} trailed {c2} by {n1} at {n2}. kys", "safety floor"),
        ("{c1} trailed {c2} by {n1} at {n2}. Bullshit lane.", "moderation list"),
    ],
)
def test_an_answer_that_breaks_a_rule_is_refused(answer: str, problem: str) -> None:
    take, problems = take_problems(slot_out(LINE, CHAMPIONS), answer, 140)
    assert take is None
    assert any(problem in found for found in problems), problems


def test_the_moderation_list_matches_whole_words_and_every_approved_line_passes() -> None:
    assert moderation_problems("what a bullshit lane")
    assert moderation_problems("what the b u l l s h i t lane")
    assert not moderation_problems("the class was cool")
    approved = [
        *(template.text for template in load_templates().templates),
        *load_moment_lines().model_dump().values(),
        *load_team_call_lines().model_dump().values(),
    ]
    assert len(approved) == 68
    assert [line for line in approved if moderation_problems(line)] == []


async def test_claude_is_sent_the_wording_and_the_style_only(tmp_path: Path) -> None:
    take = ClaudeTake(
        PIRATE_SETTINGS.model_copy(update={"model": "a-model"}), stand_in_claude(tmp_path, PIRATE)
    )
    reworded = await take.reword(LINE, CHAMPIONS, 140)
    assert reworded == "Yarr! Lee Sin sank 1,661 doubloons behind Vi by 14:00. TEAM DIFF, matey."
    (call,) = asked(tmp_path)
    question = str(call["question"])
    assert call["arguments"] == ["-p", "--output-format", "text", "--model", "a-model"]
    assert "pirate" in question
    assert "{c1}" in question
    # No champion's name and no number leaves the Mac.
    for kept_back in ("Lee Sin", "Vi ", "1,661", "14:00"):
        assert kept_back not in question.split("Line:")[1]


@pytest.mark.parametrize(
    "stand_in",
    [
        {"answer": "{c1} lost 3 to {c2} {n1} {n2}"},
        {"answer": PIRATE, "exit_code": 1},
        {"answer": PIRATE, "delay": 2.0},
    ],
)
async def test_no_take_when_the_answer_fails_or_is_late(
    tmp_path: Path, stand_in: dict[str, object]
) -> None:
    command = stand_in_claude(
        tmp_path,
        str(stand_in["answer"]),
        exit_code=int(str(stand_in.get("exit_code", 0))),
        delay=float(str(stand_in.get("delay", 0.0))),
    )
    take = ClaudeTake(PIRATE_SETTINGS, command, timeout_seconds=0.5)
    assert await take.reword(LINE, CHAMPIONS, 140) is None


async def test_a_take_is_written_in_the_background_once(tmp_path: Path) -> None:
    take = ClaudeTake(PIRATE_SETTINGS, stand_in_claude(tmp_path, PIRATE))
    assert take.take_for(LINE, CHAMPIONS, 140) == (None, True)
    assert take.take_for(LINE, CHAMPIONS, 140) == (None, True)
    for _ in range(200):
        reworded, is_pending = take.take_for(LINE, CHAMPIONS, 140)
        if not is_pending:
            break
        await asyncio.sleep(0.02)
    assert reworded is not None
    assert reworded.startswith("Yarr! Lee Sin")
    assert len(asked(tmp_path)) == 1


def test_off_or_without_the_command_there_is_no_take(tmp_path: Path) -> None:
    command = stand_in_claude(tmp_path, PIRATE)
    assert ClaudeTake(ClaudeTakeSettings(), command).take_for(LINE, CHAMPIONS, 140) == (None, False)
    assert ClaudeTake(PIRATE_SETTINGS, None).take_for(LINE, CHAMPIONS, 140) == (None, False)


def test_the_command_is_found_where_it_is_usually_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = stand_in_claude(tmp_path, PIRATE)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_claude_command() == command
    assert find_claude_command(command) == command
    assert find_claude_command(tmp_path / "missing") is None


def test_the_settings_are_kept_and_checked(tmp_path: Path) -> None:
    settings_path = tmp_path / "claude-take.json"
    assert load_claude_take_settings(settings_path) == ClaudeTakeSettings()
    save_claude_take_settings(settings_path, PIRATE_SETTINGS)
    assert load_claude_take_settings(settings_path) == PIRATE_SETTINGS
    with pytest.raises(ValidationError):
        ClaudeTakeSettings(style="x" * 201)


async def test_the_settings_page_turns_it_on_and_the_case_offers_the_take(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    settings_path = tmp_path / "claude-take.json"
    last_game = LastGameRoast(
        game=read_client_game(
            details_payload(),
            timeline_payload(),
            names_by_champion_id=champion_names(summary_payload()),
            lane_rules=LaneRules(),
        ),
        defendant_participant_id=3,
    )
    roast_path_beside(summary_path).write_text(last_game.model_dump_json())
    command = echoing_claude(tmp_path, "Yarr! ")
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            claude_take=ClaudeTake(ClaudeTakeSettings(), command),
        )
        application = create_overlay_application(
            engine, summary_path=summary_path, claude_take_path=settings_path
        )
        async with serve(application) as overlay_url:
            async with session.get(overlay_url + "/claude-take") as off_response:
                off = await off_response.json()
            async with session.put(
                overlay_url + "/claude-take", json=PIRATE_SETTINGS.model_dump()
            ) as refused:
                refused_status = refused.status
            async with session.put(
                overlay_url + "/claude-take",
                json=PIRATE_SETTINGS.model_dump(),
                headers=CLAUDE_HEADERS,
            ) as saved:
                saved_status = saved.status
            async with session.get(overlay_url + "/case") as first_response:
                first = await first_response.json()
            for _ in range(200):
                async with session.get(overlay_url + "/case") as later_response:
                    later = await later_response.json()
                if not later["claude_take_pending"]:
                    break
                await asyncio.sleep(0.02)
            async with session.get(overlay_url + "/closing-line") as copied_response:
                copied = await copied_response.json()
    assert off == {"settings": ClaudeTakeSettings().model_dump(), "is_available": True}
    assert refused_status == 403
    assert saved_status == 200
    assert load_claude_take_settings(settings_path) == PIRATE_SETTINGS
    assert (first["claude_take"], first["claude_take_pending"]) == (None, True)
    # The take keeps the closing line's numbers and names, filled back from the line itself.
    assert later["claude_take"] == "Yarr! " + later["closing_line"]
    assert copied["text"] == later["claude_take"]


async def test_during_a_game_the_shortcut_copies_the_moments_take(tmp_path: Path) -> None:
    application_of_game = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        return web.json_response(
            all_game_data(170.0, [champion_kill_event(1, 161.0, "Gank Plz", "Ahri", [])])
        )

    application_of_game.router.add_get("/liveclientdata/allgamedata", answer)
    async with serve(application_of_game) as game_url, aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, game_url, tls_context=None),
            poll_interval_seconds=0.01,
            friends=FriendsList(riot_ids=("Ahri#NA1",)),
            claude_take=ClaudeTake(PIRATE_SETTINGS, echoing_claude(tmp_path, "Yarr! ")),
        )
        stop_requested = asyncio.Event()
        engine_task = asyncio.create_task(engine.run(stop_requested))
        for _ in range(300):
            if engine.lines_to_copy and engine.lines_to_copy[-1].startswith("Yarr!"):
                break
            await asyncio.sleep(0.02)
        stop_requested.set()
        await engine_task
    assert engine.lines_to_copy == ("Yarr! Ahri gave up first blood at 2:41. Setting the tone.",)
