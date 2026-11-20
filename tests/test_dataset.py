from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cyber_loss_mcp import dataset

from . import synthetic
from .conftest import TODAY


def test_packaged_dataset_loads() -> None:
    ds = dataset.load()
    assert len(ds.incidents) == 10
    assert ds.version == dataset.DATASET_VERSION
    assert ds.digest.startswith("sha256:")
    assert ds.digest == dataset.load().digest


def test_digest_changes_with_any_byte(tmp_path: Path) -> None:
    d = synthetic.write(tmp_path / "a", [synthetic.incident(1)])
    before = dataset.load(d, TODAY).digest
    path = d / "inc-2024-synthetic-1.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert dataset.load(d, TODAY).digest != before


def test_invalid_record_stops_loading(tmp_path: Path) -> None:
    doc = synthetic.incident(1)
    doc["loss_figures"][0]["values"]["amount"] = "999"
    d = synthetic.write(tmp_path, [doc, synthetic.incident(2)])
    with pytest.raises(dataset.DatasetError, match="does not equal as_stated"):
        dataset.load(d, TODAY)


def test_supersession_is_linked_both_ways(tmp_path: Path) -> None:
    doc = synthetic.incident(1, amounts=[("$1,000,000", "1000000"), ("$2,000,000", "2000000")])
    doc["loss_figures"][1]["values"]["supersedes"] = "fig-1"
    ds = dataset.load(synthetic.write(tmp_path, [doc]), TODAY)
    f1, f2 = ds.incidents["inc-2024-synthetic-1"].figures
    assert (f1.superseded_by, f2.supersedes) == ("fig-2", "fig-1")


def test_folded_text_has_no_trailing_newline() -> None:
    inc = dataset.load().incidents["inc-2023-capita"]
    assert not inc.summary.endswith("\n")
    assert not inc.figures[0].quote.endswith("\n")


def test_only_yaml_files_are_read(tmp_path: Path) -> None:
    d = synthetic.write(tmp_path, [synthetic.incident(1)])
    shutil.copy(d / "inc-2024-synthetic-1.yaml", d / "notes.txt")
    assert list(dataset.load(d, TODAY).incidents) == ["inc-2024-synthetic-1"]
