"""Write the moderation list the safety floor checks a model's lines against (phase 11.8).

The list is LDNOOBW's English list ("List of Dirty, Naughty, Obscene, and Otherwise Bad Words",
CC BY 4.0), at a pinned commit, checked against its SHA-256. Each term is normalised as the floor
normalises a line (`roast/safety.py`) and kept only as the SHA-256 of that, so this public
repository never spells a slur out. Run it again only to move to a newer commit:

    uv run python scripts/make_moderation_list.py [--from-file en.txt]
"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import Final

from leagueasymode.roast.safety import moderation_key

SOURCE_COMMIT: Final = "5faf2ba42d7b1c0977169ec3611df25a3c08eb13"
SOURCE_URL: Final = (
    "https://raw.githubusercontent.com/LDNOOBW/"
    f"List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/{SOURCE_COMMIT}/en"
)
SOURCE_SHA256: Final = "af851ecef1d5f212caba17339b12ac39cc2fef7d78c74876f67237644fcee8bd"
OUTPUT_PATH: Final = (
    Path(__file__).resolve().parents[1] / "src/leagueasymode/roast/moderation_terms.sha256"
)
HEADER: Final = f"""\
# The moderation list the safety floor checks a model's lines against (roast/safety.py).
# Source: LDNOOBW, "List of Dirty, Naughty, Obscene, and Otherwise Bad Words", English list,
# commit {SOURCE_COMMIT} (CC BY 4.0, https://github.com/LDNOOBW).
# Each line is the SHA-256 of one term as the floor normalises it, so no term is spelled out here.
# Written by scripts/make_moderation_list.py; do not edit by hand.
"""


def main(arguments: list[str]) -> int:
    """Fetch or read the list, check it, and write its hashes.

    Args:
        arguments: The command's arguments.

    Returns:
        The exit code: 1 when the list is not the pinned one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", type=Path, help="a copy of the list, instead of fetching it")
    options = parser.parse_args(arguments)
    if options.from_file is not None:
        list_bytes = options.from_file.read_bytes()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:  # noqa: S310 - a pinned https URL
            list_bytes = response.read()
    if hashlib.sha256(list_bytes).hexdigest() != SOURCE_SHA256:
        sys.stderr.write("the list is not the pinned one; nothing written\n")
        return 1
    keys = {moderation_key(term) for term in list_bytes.decode("utf-8").splitlines()}
    hashes = sorted(hashlib.sha256(key.encode()).hexdigest() for key in keys if key)
    OUTPUT_PATH.write_text(HEADER + "\n".join(hashes) + "\n")
    sys.stdout.write(f"{len(hashes)} terms written to {OUTPUT_PATH.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
