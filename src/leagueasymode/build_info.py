"""Which build of the engine is running, as the macOS app names it.

The app passes its build ("0.1.0 (build 62, b0d63a8)": the version, CI's run number and the
commit) to the engine in `LEAGUEASYMODE_BUILD`, so that the status page, its report and each crash
report name the build; run from a clone without the app, the engine says "from source".
"""

import os
from typing import Final

from leagueasymode import __version__

BUILD_VARIABLE: Final = "LEAGUEASYMODE_BUILD"


def build_label() -> str:
    """Return the running build in words.

    Returns:
        The app's label for its build, or the engine's version "from source" without the app.
    """
    return os.environ.get(BUILD_VARIABLE) or f"{__version__} (from source)"
