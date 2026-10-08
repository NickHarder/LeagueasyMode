"""Read a directory as an Open Knowledge Format bundle: its concepts and their frontmatter.

A bundle is a tree of Markdown files. `index.md` and `log.md` are reserved at every level of it;
every other `.md` file is a concept. A concept opens with a YAML block between two `---` lines (its
frontmatter), and the rest of the file is its body.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

FRONTMATTER_DELIMITER: Final = "---"
MARKDOWN_SUFFIX: Final = ".md"
INDEX_FILE_NAME: Final = "index.md"
LOG_FILE_NAME: Final = "log.md"
HIDDEN_NAME_PREFIX: Final = "."
SKIPPED_DIRECTORY_NAMES: Final = frozenset({"node_modules", "__pycache__"})

# UTF-8, read with or without a byte-order mark in front.
TEXT_ENCODING: Final = "utf-8-sig"
TIMESTAMP_TAG: Final = "tag:yaml.org,2002:timestamp"
FIRST_FRONTMATTER_LINE_NUMBER: Final = 2


class FrontmatterLoader(yaml.SafeLoader):
    """A safe YAML loader that leaves a time as the text the author wrote.

    PyYAML follows YAML 1.1, which turns `2026-06-30T14:00:00Z` into a datetime. Every value then
    stops being what the file says, and a rule that checks how a time is written has nothing to
    check. Without that one resolver a time stays a string, as the YAML 1.2 core schema has it.
    """


FrontmatterLoader.yaml_implicit_resolvers = {
    first_character: [(tag, pattern) for tag, pattern in resolvers if tag != TIMESTAMP_TAG]
    for first_character, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class UnreadableBundleError(Exception):
    """The directory named on the command line does not exist, or a file in it cannot be read."""


class FrontmatterError(Exception):
    """A document's frontmatter is missing or cannot be read; the message says which."""


class NotAMappingError(Exception):
    """A YAML text is not valid, or is not keys and values.

    The message starts with a verb, so that whoever catches it can say what the text was.
    """


@dataclass(frozen=True)
class FrontmatterBlock:
    """The lines between a document's two `---` lines, and where they end.

    `closing_line_index` counts the file's lines from zero; `body_line_number` counts them from
    one, as a finding does.
    """

    lines: list[str]
    closing_line_index: int
    body_line_number: int


@dataclass(frozen=True)
class Document:
    """One Markdown file of a bundle, split into its frontmatter and its body.

    `path` is what a finding shows: the bundle as it was named on the command line, then the file's
    place inside it. `frontmatter_problem` says why the frontmatter could not be read, when it
    could not; `fields` is then empty.
    """

    path: Path
    relative_path: Path
    fields: dict[str, object]
    line_number_by_key: dict[str, int]
    frontmatter_problem: str | None
    body: str
    body_line_number: int

    def line_number_of(self, key: str) -> int:
        """Return the line a top-level frontmatter key is on, or 1 when the key is not there."""
        return self.line_number_by_key.get(key, 1)

    def text_field(self, key: str) -> str:
        """Return a frontmatter value when it is text with something in it, else an empty string."""
        value = self.fields.get(key)
        return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class Bundle:
    """A bundle as it is on disk: its concepts, its logs, and the files that are not Markdown.

    Index files are not held here: they are written from everything else (see `okf.index`).
    """

    directory: Path
    concepts: list[Document]
    log_files: list[Path]
    other_files: list[Path]


def frontmatter_block(lines: list[str]) -> FrontmatterBlock:
    """Return the frontmatter lines of a document.

    Raises:
        FrontmatterError: If the file does not start with a `---` line, or never closes it.
    """
    if not lines or lines[0].rstrip() != FRONTMATTER_DELIMITER:
        message = "the file must start with frontmatter: a `---` line, YAML, then a `---` line"
        raise FrontmatterError(message)
    closing_indexes = [
        line_index
        for line_index, line in enumerate(lines)
        if line_index > 0 and line.rstrip() == FRONTMATTER_DELIMITER
    ]
    if not closing_indexes:
        message = "the frontmatter is never closed; add a `---` line after it"
        raise FrontmatterError(message)
    closing_index = closing_indexes[0]
    return FrontmatterBlock(
        lines=lines[1:closing_index],
        closing_line_index=closing_index,
        body_line_number=closing_index + 2,
    )


def yaml_mapping(yaml_text: str) -> dict[str, object]:
    """Return the top-level keys and values of a YAML text; none for an empty one.

    Raises:
        NotAMappingError: If the text is not valid YAML, or is not a mapping of keys to values.
    """
    loader = FrontmatterLoader(yaml_text)
    try:
        loaded: object = loader.get_single_data()
    except yaml.YAMLError as error:
        message = f"is not valid YAML: {' '.join(str(error).split())}"
        raise NotAMappingError(message) from error
    # A value that carries a tag (`!!int Metric`) is built by code that fails in its own way for
    # each tag, and a text nested deeply enough runs out of stack. Every way is the same answer.
    except Exception as error:
        message = f"is not valid YAML: a value cannot be read as what its tag says ({error!r})"
        raise NotAMappingError(message) from error
    finally:
        loader.dispose()
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        message = "must be keys and values, such as `type: Metric`"
        raise NotAMappingError(message)
    return {str(key): value for key, value in loaded.items()}


def frontmatter_fields(block_lines: list[str]) -> dict[str, object]:
    """Return the top-level keys and values of a frontmatter block.

    Raises:
        FrontmatterError: If the block is not valid YAML, or is not a mapping of keys to values.
    """
    try:
        return yaml_mapping("\n".join(block_lines))
    except NotAMappingError as error:
        message = f"the frontmatter {error}"
        raise FrontmatterError(message) from error


def top_level_nodes(block_lines: list[str]) -> list[tuple[str, yaml.Node, yaml.Node]]:
    """Return each top-level key of a frontmatter block with where it and its value are written.

    The YAML reader says where: a line of a quoted text can look like a key, and is not one. Each
    entry is the key, its node and its value's node, in the order written. Lines and columns in a
    node count from zero, within the block. A block that is not keys and values gives nothing.
    """
    loader = FrontmatterLoader("\n".join(block_lines))
    try:
        root_node = loader.get_single_node()
    except (yaml.YAMLError, RecursionError):
        return []
    finally:
        loader.dispose()
    if not isinstance(root_node, yaml.MappingNode):
        return []
    return [
        (str(key_node.value), key_node, value_node)
        for key_node, value_node in root_node.value
        if isinstance(key_node, yaml.ScalarNode)
    ]


def key_line_numbers(yaml_text: str, parent_key: str | None = None) -> dict[str, int]:
    """Return the line each key of a YAML text is on: its top-level keys, or the keys under one.

    Lines count from one. A text that is not keys and values has none, and neither has a parent
    key that is not there or does not hold keys and values.
    """
    top_level = top_level_nodes(yaml_text.splitlines())
    if parent_key is None:
        return {key: key_node.start_mark.line + 1 for key, key_node, _value in reversed(top_level)}
    parent_nodes = [value_node for key, _key_node, value_node in top_level if key == parent_key]
    if not parent_nodes or not isinstance(parent_nodes[-1], yaml.MappingNode):
        return {}
    return {
        str(key_node.value): key_node.start_mark.line + 1
        for key_node, _value_node in reversed(parent_nodes[-1].value)
        if isinstance(key_node, yaml.ScalarNode)
    }


def read_text_file(file_path: Path) -> str:
    """Return a file's text, without the byte-order mark some editors put in front of it.

    Raises:
        UnreadableBundleError: If the file cannot be read as text.
    """
    try:
        return file_path.read_text(encoding=TEXT_ENCODING)
    except (OSError, UnicodeDecodeError) as error:
        message = f"{file_path} could not be read: {error}"
        raise UnreadableBundleError(message) from error


def read_document(bundle_directory: Path, document_file: Path) -> Document:
    """Return one file of the bundle, with its frontmatter read or the reason it could not be.

    Raises:
        UnreadableBundleError: If the file cannot be read as text.
    """
    text = read_text_file(document_file)
    lines = text.splitlines()
    relative_path = document_file.relative_to(bundle_directory)
    try:
        block = frontmatter_block(lines)
        fields = frontmatter_fields(block.lines)
    except FrontmatterError as error:
        return Document(
            path=document_file,
            relative_path=relative_path,
            fields={},
            line_number_by_key={},
            frontmatter_problem=str(error),
            body=text,
            body_line_number=1,
        )
    return Document(
        path=document_file,
        relative_path=relative_path,
        fields=fields,
        line_number_by_key={
            key: line_number + FIRST_FRONTMATTER_LINE_NUMBER - 1
            for key, line_number in key_line_numbers("\n".join(block.lines)).items()
        },
        frontmatter_problem=None,
        body="\n".join(lines[block.body_line_number - 1 :]),
        body_line_number=block.body_line_number,
    )


def is_listed(relative_path: Path) -> bool:
    """Return whether a file belongs to the bundle: not hidden, and not in a tool's directory."""
    return not any(
        part.startswith(HIDDEN_NAME_PREFIX) or part in SKIPPED_DIRECTORY_NAMES
        for part in relative_path.parts
    )


def bundle_files(bundle_directory: Path) -> list[Path]:
    """Return every file of the bundle, in the order of their paths.

    Raises:
        UnreadableBundleError: If the directory does not exist.
    """
    if not bundle_directory.is_dir():
        message = f"{bundle_directory} does not exist, or is not a directory"
        raise UnreadableBundleError(message)
    relative_paths = sorted(
        (
            candidate.relative_to(bundle_directory)
            for candidate in bundle_directory.rglob("*")
            if candidate.is_file()
        ),
        key=lambda relative_path: relative_path.as_posix(),
    )
    return [
        bundle_directory / relative_path
        for relative_path in relative_paths
        if is_listed(relative_path)
    ]


def read_bundle(bundle_directory: Path) -> Bundle:
    """Return the bundle in a directory: every concept read, every other file named.

    Raises:
        UnreadableBundleError: If the directory does not exist, or a file cannot be read.
    """
    files = bundle_files(bundle_directory)
    markdown_files = [file for file in files if file.suffix == MARKDOWN_SUFFIX]
    return Bundle(
        directory=bundle_directory,
        concepts=[
            read_document(bundle_directory, markdown_file)
            for markdown_file in markdown_files
            if markdown_file.name not in {INDEX_FILE_NAME, LOG_FILE_NAME}
        ],
        log_files=[file for file in markdown_files if file.name == LOG_FILE_NAME],
        other_files=[file for file in files if file.suffix != MARKDOWN_SUFFIX],
    )
