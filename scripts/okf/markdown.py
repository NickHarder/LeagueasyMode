"""Read Markdown the way the rules need it: the lines that are prose, the links, and the code.

A rule looks at what a document states. An example states nothing, so no rule reads a line inside
a code fence, a line indented by four spaces or a tab, text between backticks, or an HTML comment.
Every rule reads Markdown through this module, so that all of them agree on which is which.

Where this reader and a Markdown renderer could disagree, it takes the reading that reports less.
A line indented by four spaces is never prose, even where a renderer would show it as part of a
list: a broken link there is missed, and a code sample is never reported.
"""

import re
import textwrap
from dataclasses import dataclass
from typing import Final

PROSE: Final = "prose"
FENCE_LINE: Final = "fence line"
FENCED_CODE: Final = "fenced code"
INDENTED: Final = "indented"
COMMENT: Final = "comment"
CODE_SPAN: Final = "code span"

# A fence opens with three or more backticks or tildes, and closes with at least as many. In a
# quotation, it follows the quotation's `>` marks.
FENCE_PATTERN: Final = re.compile(r"[\s>]*(?P<run>`{3,}|~{3,})(?P<rest>.*)")
BACKTICK: Final = "`"
INDENTED_CODE_PREFIXES: Final = ("    ", "\t")
COMMENT_OPENING: Final = "<!--"
COMMENT_CLOSING: Final = "-->"
CLOSED_COMMENT_PATTERN: Final = re.compile(r"<!--.*?-->")
# What opens a comment, or a code span, that its line leaves open.
OPENING_PATTERN: Final = re.compile(r"<!--|`+")
# A code span opens with a run of backticks and closes with a run of the same length.
CODE_SPAN_PATTERN: Final = re.compile(r"(?<!`)(?P<run>`+)(?!`).*?(?<!`)(?P=run)(?!`)")
# A heading may be indented by up to three spaces, and may be closed with a run of `#`.
HEADING_PATTERN: Final = re.compile(r"\s{0,3}(?P<marks>#{1,6})(?:\s+(?P<text>.*?))?(?:\s+#+)?\s*")
LIST_ITEM_PATTERN: Final = re.compile(r"\s{0,3}(?:[-*+]|\d{1,9}[.)])(?:\s|$)")
LIST_CONTENT_INDENT: Final = "  "

# Where a link leads: between angle brackets, or a run with no space whose parentheses pair up.
DESTINATION: Final = (
    r"(?:<(?P<bracketed>(?:[^<>\\]|\\.)*)>"
    r"|(?P<bare>(?:[^\s()<>]|\((?:[^\s()]|\([^\s()]*\))*\))+))"
)
TITLE: Final = r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^()]*\)))?"""
# [text](destination) and ![text](destination), with an optional title after the destination.
INLINE_LINK_PATTERN: Final = re.compile(rf"!?\[(?P<text>[^\]]*)\]\(\s*{DESTINATION}{TITLE}\s*\)")
# [label]: destination, the second half of a link written as a reference, and nothing after it but
# a title. A footnote's label starts with ^ and is not a link.
REFERENCE_DEFINITION_PATTERN: Final = re.compile(
    rf"(?P<label>\s{{0,3}}\[[^\]^][^\]]*\]):\s*{DESTINATION}{TITLE}\s*"
)
ESCAPED_PUNCTUATION_PATTERN: Final = re.compile(r"\\(?P<character>[!-/:-@\[-`{-~])")
# <https://example.com>, and an address written out with no brackets round it.
AUTOLINK_PATTERN: Final = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*:[^<>\s]*>")
WRITTEN_OUT_ADDRESS_PATTERN: Final = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://\S+")


@dataclass(frozen=True)
class Fence:
    """An open code fence: the character it was opened with, and how many of them."""

    character: str
    length: int


@dataclass(frozen=True)
class MarkdownLine:
    """One line of a Markdown text, and what kind of line it is.

    `written` is the line as it is in the file. `text` is what the line states: for a line of
    prose, the line without its code spans and its comments; for any other kind, nothing.
    """

    line_number: int
    written: str
    kind: str
    text: str


@dataclass(frozen=True)
class ProseLine:
    """One line that is prose, with its code spans and its comments taken out."""

    line_number: int
    text: str


@dataclass(frozen=True)
class Heading:
    """A heading: how many `#` it has, and its text without them."""

    level: int
    text: str


@dataclass(frozen=True)
class Link:
    """One link: the line it is on, and where it leads, as written."""

    line_number: int
    target: str


def opening_fence_of(line: str) -> Fence | None:
    """Return the fence a line opens, or None when it opens none."""
    matched = FENCE_PATTERN.fullmatch(line)
    if matched is None:
        return None
    run: str = matched.group("run")
    # Three backticks, some text and three more on one line are a code span, not a fence.
    if run.startswith(BACKTICK) and BACKTICK in matched.group("rest"):
        return None
    return Fence(character=run[0], length=len(run))


def closes(line: str, fence: Fence) -> bool:
    """Return whether a line closes a fence: the same character, at least as many, nothing else."""
    stripped_line = line.lstrip(" \t>").strip()
    return len(stripped_line) >= fence.length and set(stripped_line) == {fence.character}


def stated_text(line: str) -> tuple[str, str]:
    """Return what a line of prose states, and what closes a comment or a code span it leaves open.

    The second is `-->`, or the run of backticks that opened the span; empty when nothing is left
    open. The code spans go first, so that a comment marker shown as code opens nothing.
    """
    without_code_spans = CODE_SPAN_PATTERN.sub("", line)
    without_closed_comments = CLOSED_COMMENT_PATTERN.sub("", without_code_spans)
    opening = OPENING_PATTERN.search(without_closed_comments)
    if opening is None:
        return without_closed_comments, ""
    closing = COMMENT_CLOSING if opening.group() == COMMENT_OPENING else opening.group()
    return without_closed_comments[: opening.start()], closing


def markdown_lines(text: str, first_line_number: int = 1) -> list[MarkdownLine]:
    """Return every line of a text with its kind, numbered as the lines are in the file."""
    found_lines: list[MarkdownLine] = []
    open_fence: Fence | None = None
    # What closes the comment or the code span that an earlier line left open; empty when none is.
    waited_for = ""
    for line_index, line in enumerate(text.splitlines()):
        line_number = line_index + first_line_number
        if open_fence is not None:
            is_the_closing_line = closes(line, open_fence)
            kind_in_a_fence = FENCE_LINE if is_the_closing_line else FENCED_CODE
            found_lines.append(MarkdownLine(line_number, line, kind_in_a_fence, ""))
            open_fence = None if is_the_closing_line else open_fence
            continue
        if waited_for == COMMENT_CLOSING:
            closing_index = line.find(COMMENT_CLOSING)
            if closing_index < 0:
                found_lines.append(MarkdownLine(line_number, line, COMMENT, ""))
                continue
            text_after_the_comment, waited_for = stated_text(
                line[closing_index + len(COMMENT_CLOSING) :]
            )
            found_lines.append(MarkdownLine(line_number, line, PROSE, text_after_the_comment))
            continue
        # A fence ends the paragraph it follows, and any code span left open in it.
        open_fence = opening_fence_of(line)
        if open_fence is not None:
            waited_for = ""
            found_lines.append(MarkdownLine(line_number, line, FENCE_LINE, ""))
            continue
        # A code span runs on to a run of backticks as long as the one that opened it, or to the
        # blank line that ends its paragraph.
        if waited_for and line.strip():
            closing_run = re.search(rf"(?<!`){waited_for}(?!`)", line)
            if closing_run is None:
                found_lines.append(MarkdownLine(line_number, line, CODE_SPAN, ""))
                continue
            text_after_the_span, waited_for = stated_text(line[closing_run.end() :])
            found_lines.append(MarkdownLine(line_number, line, PROSE, text_after_the_span))
            continue
        if line.startswith(INDENTED_CODE_PREFIXES) and line.strip():
            found_lines.append(MarkdownLine(line_number, line, INDENTED, ""))
            continue
        text_of_the_line, waited_for = stated_text(line)
        found_lines.append(MarkdownLine(line_number, line, PROSE, text_of_the_line))
    return found_lines


def prose_lines(text: str, first_line_number: int = 1) -> list[ProseLine]:
    """Return the lines of a text that are prose, numbered as they are in the file."""
    return [
        ProseLine(line_number=line.line_number, text=line.text)
        for line in markdown_lines(text, first_line_number)
        if line.kind == PROSE
    ]


def heading_of(line_text: str) -> Heading | None:
    """Return the heading a line of prose is, or None when it is not one."""
    matched = HEADING_PATTERN.fullmatch(line_text)
    if matched is None:
        return None
    return Heading(level=len(matched.group("marks")), text=matched.group("text") or "")


def destination_of(matched: re.Match[str]) -> str:
    """Return where a matched link leads, without the angle brackets or the escapes round it."""
    written: str = matched.group("bracketed") or matched.group("bare") or ""
    return ESCAPED_PUNCTUATION_PATTERN.sub(lambda escaped: escaped.group("character"), written)


def links_in(lines: list[ProseLine]) -> list[Link]:
    """Return every link in the prose, in the order of the lines they are on."""
    inline_links = [
        Link(line_number=line.line_number, target=destination_of(matched))
        for line in lines
        for matched in INLINE_LINK_PATTERN.finditer(line.text)
    ]
    reference_matches = [
        (line.line_number, REFERENCE_DEFINITION_PATTERN.fullmatch(line.text)) for line in lines
    ]
    reference_links = [
        Link(line_number=line_number, target=destination_of(matched))
        for line_number, matched in reference_matches
        if matched is not None
    ]
    return sorted([*inline_links, *reference_links], key=lambda link: link.line_number)


def without_addresses(line_text: str) -> str:
    """Return a line of prose without the places its links lead to.

    An address names a place. A word inside it says nothing about this project, whatever it looks
    like: the ticket number at the end of a tracker's URL is not one of this project's ids.
    """
    reference_definition = REFERENCE_DEFINITION_PATTERN.fullmatch(line_text)
    if reference_definition is not None:
        label: str = reference_definition.group("label")
        return label
    without_destinations = INLINE_LINK_PATTERN.sub(
        lambda matched: f"[{matched.group('text')}]", line_text
    )
    without_autolinks = AUTOLINK_PATTERN.sub("", without_destinations)
    return WRITTEN_OUT_ADDRESS_PATTERN.sub("", without_autolinks)


def code_blocks(lines: list[MarkdownLine]) -> list[str]:
    """Return the blocks of code among some lines, each without its fence or its indent.

    A block is what a fence holds, wherever the fence is. Or it is a run of indented lines that
    starts after a blank line and outside a list: an indented line that follows a line of text
    carries that text on, and an indented line in a list belongs to its item.
    """
    blocks: list[str] = []
    block_lines: list[str] = []
    blank_line_count = 0
    is_in_a_fence = False
    is_in_a_list = False
    follows_a_blank_line = True
    for line in lines:
        is_blank = not line.written.strip()
        if line.kind == FENCED_CODE:
            block_lines.append(line.written)
        elif line.kind == FENCE_LINE:
            # The opening line ends an indented block before it; the closing line ends its own.
            if is_in_a_fence or block_lines:
                blocks.append(textwrap.dedent("\n".join(block_lines)))
                block_lines.clear()
            is_in_a_fence = not is_in_a_fence
        elif is_blank:
            blank_line_count += 1
        elif line.kind == INDENTED:
            if block_lines:
                block_lines.extend([""] * blank_line_count)
                block_lines.append(line.written)
            elif follows_a_blank_line and not is_in_a_list:
                block_lines.append(line.written)
        else:
            if block_lines:
                blocks.append(textwrap.dedent("\n".join(block_lines)))
                block_lines.clear()
            is_a_list_item = (
                line.kind == PROSE and LIST_ITEM_PATTERN.match(line.written) is not None
            )
            ends_the_list = follows_a_blank_line and not line.written.startswith(
                LIST_CONTENT_INDENT
            )
            is_in_a_list = is_a_list_item or (is_in_a_list and not ends_the_list)
        blank_line_count = blank_line_count if is_blank else 0
        follows_a_blank_line = is_blank
    return [*blocks, *([textwrap.dedent("\n".join(block_lines))] if block_lines else [])]
