"""Which build of the engine is running, as the macOS app names it.

The app passes its build ("0.1.0 (build 62, b0d63a8)": the version, CI's run number and the
commit) to the engine in `LEAGUEASYMODE_BUILD`, so that the status page, its report and each crash
report name the build; run from a clone without the app, the engine says "from source".
"""

import os
from pathlib import Path
from typing import Final

from leagueasymode import __version__

BUILD_VARIABLE: Final = "LEAGUEASYMODE_BUILD"
# Where the macOS app writes the engine's output, which a problem report takes the end of.
ENGINE_LOG_VARIABLE: Final = "LEAGUEASYMODE_ENGINE_LOG"


def build_label() -> str:
    """Return the running build in words.

    Returns:
        The app's label for its build, or the engine's version "from source" without the app.
    """
    return os.environ.get(BUILD_VARIABLE) or f"{__version__} (from source)"


def engine_log_path() -> Path | None:
    """Return the log the macOS app writes the engine's output to.

    Returns:
        The log; None without the app, or when it keeps none.
    """
    log_path = os.environ.get(ENGINE_LOG_VARIABLE)
    return Path(log_path) if log_path else None
