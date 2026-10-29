"""A roast line as parts: plain text, and slots whose text is an exhibit's value, with its key."""

from pydantic import BaseModel, ConfigDict


class LinePart(BaseModel):
    """A piece of a line. A part with an exhibit key is that exhibit's value, and cites it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    exhibit_key: str | None = None


class CitedLine(BaseModel):
    """One line of a roast, the template it came from and the players it names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    parts: tuple[LinePart, ...]
    champion_participant_ids: tuple[int, ...]
    # The player the line is about, whether or not it names their champion.
    subject_participant_id: int | None = None

    @property
    def text(self) -> str:
        """Return the line as it reads, without its citations.

        Returns:
            The text.
        """
        return "".join(part.text for part in self.parts)

    @property
    def exhibit_keys(self) -> tuple[str, ...]:
        """Return the keys of the exhibits the line cites, each once, in order.

        Returns:
            The exhibit keys.
        """
        cited_keys = [part.exhibit_key for part in self.parts if part.exhibit_key is not None]
        return tuple(dict.fromkeys(cited_keys))
