"""One way to save a file whole (audit ARCH-04)."""

import concurrent.futures
from pathlib import Path

import pytest

from leagueasymode.atomic_write import write_whole
from leagueasymode.overlay_state import OverlayLayout, WidgetOffset
from leagueasymode.preferences import load_layout, save_layout


def test_saves_of_one_file_at_the_same_time_never_collide(tmp_path: Path) -> None:
    # Audit ARCH-04: every save went through one fixed `.partial` name, so two at once (a widget
    # dragged while another is resized) could rename it from under each other and fail or lose one.
    layout_path = tmp_path / "layout.json"
    layouts = [
        OverlayLayout(offsets={"you_panel": WidgetOffset(x_share=index / 100, y_share=0.0)})
        for index in range(40)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda layout: save_layout(layout_path, layout), layouts))
    assert load_layout(layout_path) in layouts
    assert [path.name for path in tmp_path.iterdir()] == ["layout.json"]


def test_a_write_that_fails_leaves_the_file_as_it_was_and_nothing_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = tmp_path / "settings.json"
    write_whole(file_path, "before\n")

    def refuse(_self: Path, _target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        write_whole(file_path, "after\n")
    monkeypatch.undo()
    assert file_path.read_text() == "before\n"
    assert [path.name for path in tmp_path.iterdir()] == ["settings.json"]


def test_bytes_are_written_as_they_are(tmp_path: Path) -> None:
    file_path = tmp_path / "nested" / "data.bin"
    write_whole(file_path, b"\x00\x01")
    assert file_path.read_bytes() == b"\x00\x01"
