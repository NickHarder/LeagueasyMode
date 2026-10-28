"""Claude's take (phase 11.8): a line that passed the checks, reworded by the `claude` command.

The owner, 2026-10-28: "could leaguse mode interface with claude local cli so it can add some
variety and custom spice to roasts". With the setting on, each line the shortcut can copy (the
post-game closing line, a moment about a friend, a team call) is sent to the `claude` command on
the Mac, with the owner's own Claude login, to be reworded in the style the owner sets.

Claude writes the words, never the numbers or the names. Every number and every champion's name in
the line becomes a slot ("{n1}", "{c1}") before it is sent, so nothing but the line's wording and
the style leaves the Mac; the engine fills the slots back from the line itself. The answer is then
checked like any line, and more: every slot kept once and none added, no digit outside a slot, no
capitalised name that was not there, one line within the chat limit, the safety floor and the
moderation list. Any failure, or no answer within the time limit, and the approved line stands.

Rewording takes seconds, so it runs in the background: the approved line is ready at once, and
Claude's take replaces it for copying when it arrives. The tests never call Claude; a stand-in
`claude` answers with canned text.
"""

import asyncio
import logging
import os
import re
import shutil
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from leagueasymode.roast.safety import floor_problems, moderation_problems

logger = logging.getLogger(__name__)

CLAUDE_COMMAND_NAME: Final = "claude"
# Where the `claude` command is often installed on a Mac, beside what PATH says: an app started
# from Finder has a short PATH.
EXTRA_COMMAND_DIRECTORIES: Final = (
    "~/.local/bin",
    "~/.claude/local",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)
ANSWER_TIMEOUT_SECONDS: Final = 30.0
NUMBER_PATTERN: Final = re.compile(r"[-+]?\d[\d,]*(?:[.:]\d+)?%?k?")
SLOT_PATTERN: Final = re.compile(r"\{\w+\}")
CAPITALISED_WORD_PATTERN: Final = re.compile(r"[A-Z][\w']*")
SENTENCE_ENDS: Final = ".!?"
LONGEST_STYLE_CHARACTERS: Final = 200
LONGEST_MODEL_CHARACTERS: Final = 80
PROMPT: Final = """\
Reword this one line from a League of Legends overlay, to be pasted in game chat, in this style: \
{style}

Rules:
- Keep every placeholder in braces exactly as written, each once: {slots}. They stand for numbers \
and champions' names, which are filled in afterwards.
- Add no numbers, no names and no new facts. Only gameplay.
- No slurs, and nothing about anyone's identity, looks, family or self-harm.
- At most {limit} characters once the placeholders are filled in.
- Answer with the reworded line only, on one line.

Line: {template}
"""


class ClaudeTakeSettings(BaseModel):
    """The owner's choices for Claude's take, from the settings page; off until turned on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    # The style, in the owner's words, such as "pirate" or "sports commentator".
    style: str = Field(default="", max_length=LONGEST_STYLE_CHARACTERS)
    # The model the `claude` command uses; empty for the command's own default.
    model: str = Field(default="", max_length=LONGEST_MODEL_CHARACTERS)


@dataclass(frozen=True)
class SlottedLine:
    """A line with its numbers and champions' names taken out into slots."""

    template: str
    values: dict[str, str]


def slot_out(text: str, champion_names: frozenset[str]) -> SlottedLine:
    """Take a line's champions' names and numbers out into slots.

    Args:
        text: The approved line.
        champion_names: The champions in the game.

    Returns:
        The line with "{c1}", "{n1}" and so on in their place, and what each slot holds.
    """
    values: dict[str, str] = {}
    template = text.replace("{", "{{").replace("}", "}}")
    for name in sorted(champion_names, key=len, reverse=True):
        if name and name in template:
            slot = f"c{sum(1 for key in values if key.startswith('c')) + 1}"
            values[slot] = name
            template = template.replace(name, "{" + slot + "}")
    pieces: list[str] = []
    last_end = 0
    for match in NUMBER_PATTERN.finditer(template):
        inside_slot = template[: match.start()].count("{") > template[: match.start()].count("}")
        if inside_slot:
            continue
        slot = f"n{sum(1 for key in values if key.startswith('n')) + 1}"
        values[slot] = match.group(0)
        pieces.extend([template[last_end : match.start()], "{" + slot + "}"])
        last_end = match.end()
    pieces.append(template[last_end:])
    return SlottedLine(template="".join(pieces), values=values)


def take_problems(
    original: SlottedLine, answer: str, limit_characters: int
) -> tuple[str | None, list[str]]:
    """Check Claude's answer, and fill its slots when it passes.

    Args:
        original: The approved line, slotted out.
        answer: What Claude answered.
        limit_characters: The longest line chat takes.

    Returns:
        The filled line, or None, and every problem found.
    """
    answer_lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    if len(answer_lines) != 1:
        return None, ["the answer is not one line"]
    reworded = answer_lines[0].strip("\"'“”")
    try:
        fields = [field for _, field, _, _ in string.Formatter().parse(reworded) if field]
    except ValueError:
        return None, ["the answer's braces cannot be read"]
    problems: list[str] = []
    if sorted(fields) != sorted(original.values):
        problems.append("the answer does not keep each slot exactly once")
    words_outside_slots = SLOT_PATTERN.sub(" ", reworded)
    if re.search(r"\d", words_outside_slots):
        problems.append("the answer has a number outside a slot")
    original_words = set(CAPITALISED_WORD_PATTERN.findall(SLOT_PATTERN.sub(" ", original.template)))
    if _new_names(words_outside_slots, original_words):
        problems.append("the answer names something the line did not")
    if problems:
        return None, problems
    filled = reworded.format(**original.values)
    if len(filled) > limit_characters:
        problems.append(f"the answer is longer than {limit_characters} characters")
    problems.extend(floor_problems(filled))
    problems.extend(moderation_problems(filled))
    return (None, problems) if problems else (filled, [])


def _new_names(text: str, known_words: set[str]) -> set[str]:
    """Return the capitalised words of a text that may be names it was not given.

    A capitalised word that starts a sentence is a sentence's start, and "I" is no name.

    Args:
        text: The answer, its slots taken out.
        known_words: The capitalised words of the approved line.

    Returns:
        The words that are capitalised mid-sentence and not in the approved line.
    """
    names: set[str] = set()
    for match in CAPITALISED_WORD_PATTERN.finditer(text):
        before = text[: match.start()].rstrip()
        starts_a_sentence = not before or before[-1] in SENTENCE_ENDS
        word = match.group(0)
        if not starts_a_sentence and word not in known_words and word != "I":
            names.add(word)
    return names


def find_claude_command(configured: Path | None = None) -> Path | None:
    """Return the `claude` command to run, if it is installed.

    Args:
        configured: The command the settings name (`LEAGUEASYMODE_CLAUDE_COMMAND`); None to look.

    Returns:
        The command, or None when it is not found.
    """
    if configured is not None:
        return configured if configured.is_file() else None
    search_path = os.pathsep.join(
        [
            os.environ.get("PATH", ""),
            *(str(Path(directory).expanduser()) for directory in EXTRA_COMMAND_DIRECTORIES),
        ]
    )
    found = shutil.which(CLAUDE_COMMAND_NAME, path=search_path)
    return Path(found) if found is not None else None


async def ask_claude(
    command: Path, prompt: str, model: str, timeout_seconds: float = ANSWER_TIMEOUT_SECONDS
) -> str | None:
    """Ask the `claude` command one question, in print mode, and return its answer.

    Args:
        command: The `claude` command.
        prompt: The question, sent on standard input.
        model: The model to ask; empty for the command's default.
        timeout_seconds: How long to wait.

    Returns:
        The answer, or None when the command failed or took too long.
    """
    arguments = ["-p", "--output-format", "text", *(["--model", model] if model else [])]
    try:
        process = await asyncio.create_subprocess_exec(
            str(command),
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        logger.warning("could not start the claude command")
        return None
    try:
        answer_bytes, _ = await asyncio.wait_for(
            process.communicate(prompt.encode()), timeout=timeout_seconds
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        logger.warning("the claude command took too long; the approved line stands")
        return None
    if process.returncode != 0:
        logger.warning("the claude command failed (exit %s)", process.returncode)
        return None
    return answer_bytes.decode("utf-8", errors="replace")


@dataclass
class ClaudeTake:
    """Rewords lines in the background, and remembers each answer for this run."""

    settings: ClaudeTakeSettings
    command: Path | None
    timeout_seconds: float = ANSWER_TIMEOUT_SECONDS
    # Each line's take by (line, style, model): the filled line, or None when it failed.
    _takes: dict[tuple[str, str, str], str | None] = field(default_factory=dict)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set)

    @property
    def is_available(self) -> bool:
        """Whether the `claude` command was found."""
        return self.command is not None

    def set_settings(self, settings: ClaudeTakeSettings) -> None:
        """Take the owner's new choices; takes in an earlier style are kept but not used.

        Args:
            settings: The choices.
        """
        self.settings = settings

    def take_for(
        self, text: str, champion_names: frozenset[str], limit_characters: int
    ) -> tuple[str | None, bool]:
        """Return Claude's take of a line when it is ready, and start one when none is.

        Args:
            text: The approved line.
            champion_names: The champions in the game.
            limit_characters: The longest line chat takes.

        Returns:
            The take or None, and whether one is still being written.
        """
        settings = self.settings
        if not settings.enabled or self.command is None:
            return None, False
        key = (text, settings.style, settings.model)
        if key in self._takes:
            return self._takes[key], False
        if not any(not task.done() and task.get_name() == repr(key) for task in self._tasks):
            task = asyncio.get_running_loop().create_task(
                self._write(key, champion_names, limit_characters), name=repr(key)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return None, True

    async def reword(
        self, text: str, champion_names: frozenset[str], limit_characters: int
    ) -> str | None:
        """Ask Claude for a take of a line now, and check it.

        Args:
            text: The approved line.
            champion_names: The champions in the game.
            limit_characters: The longest line chat takes.

        Returns:
            The take, or None when there is none that passes.
        """
        command = self.command
        if command is None:
            return None
        slotted = slot_out(text, champion_names)
        style = self.settings.style.strip() or "playful trash talk between friends"
        prompt = PROMPT.format(
            style=style,
            slots=", ".join("{" + slot + "}" for slot in slotted.values) or "none",
            limit=limit_characters,
            template=slotted.template,
        )
        answer = await ask_claude(command, prompt, self.settings.model, self.timeout_seconds)
        if answer is None:
            return None
        take, problems = take_problems(slotted, answer, limit_characters)
        if problems:
            logger.info("Claude's take was refused: %s", "; ".join(problems))
        return take

    async def _write(
        self, key: tuple[str, str, str], champion_names: frozenset[str], limit_characters: int
    ) -> None:
        """Write one take and keep it, or keep that there is none."""
        self._takes[key] = await self.reword(key[0], champion_names, limit_characters)


def load_claude_take_settings(settings_path: Path) -> ClaudeTakeSettings:
    """Return the owner's choices for Claude's take.

    Args:
        settings_path: The file.

    Returns:
        The choices; off when the file is missing or cannot be read.
    """
    try:
        return ClaudeTakeSettings.model_validate_json(settings_path.read_text())
    except FileNotFoundError:
        return ClaudeTakeSettings()
    except (OSError, ValidationError):
        logger.warning("could not read Claude's take's settings; it stays off")
        return ClaudeTakeSettings()


def save_claude_take_settings(settings_path: Path, settings: ClaudeTakeSettings) -> None:
    """Keep the owner's choices for Claude's take, replacing the file whole.

    Args:
        settings_path: The file.
        settings: The choices.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = settings_path.with_suffix(".partial")
    partial_path.write_text(settings.model_dump_json(indent=2) + "\n")
    partial_path.replace(settings_path)
