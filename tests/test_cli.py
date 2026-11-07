from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cyber_loss_mcp.validation import cli, paths

from .conftest import INCIDENT_FIXTURE

ROOT = Path(__file__).parent.parent


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the logs plus an empty incidents directory standing in for the package's."""
    shutil.copytree(ROOT / "logs", tmp_path / "logs")
    incidents = tmp_path / "incidents"
    incidents.mkdir()
    (incidents / ".gitkeep").touch()
    monkeypatch.setattr(paths, "INCIDENTS", incidents)
    return tmp_path


def run(repo: Path, *extra: str) -> int:
    return cli.main(["--root", str(repo), "--today", "2026-11-06", *extra])


def test_clean_dataset_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo) == 0
    assert "0 incident records checked; 0 errors" in capsys.readouterr().out


def test_valid_record_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copy(INCIDENT_FIXTURE, repo / "incidents")
    assert run(repo) == 0
    assert "1 incident records checked; 0 errors" in capsys.readouterr().out


def test_invalid_record_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = INCIDENT_FIXTURE.read_text(encoding="utf-8").replace("'12300000'", "'12345678'")
    (repo / "incidents" / INCIDENT_FIXTURE.name).write_text(text, encoding="utf-8")
    assert run(repo) == 1
    assert "does not equal as_stated" in capsys.readouterr().err


def test_stray_file_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "incidents" / "notes.yml").write_text("a: 1\n", encoding="utf-8")
    assert run(repo) == 1
    assert "only .yaml incident records" in capsys.readouterr().err


def test_missing_log_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "logs" / "corrections.yaml").unlink()
    assert run(repo) == 1
    assert "log file is missing" in capsys.readouterr().err


def test_base_ref_detects_edited_log(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = (
        "entries:\n- id: unv-1\n  date: '2026-11-01'\n  organisation: Example\n"
        "  claim: $1 million\n  seen_in: news\n  reason: {reason}\n  status: open\n"
        "  supersedes: none\n"
    )
    log = repo / "logs" / "unverified.yaml"
    head = log.read_text(encoding="utf-8").replace("entries: []\n", "")
    log.write_text(head + entry.format(reason="edited"), encoding="utf-8")
    base = head + entry.format(reason="original")
    monkeypatch.setattr(
        cli, "_git_show", lambda ref, path: base if path.endswith("unverified.yaml") else None
    )
    assert run(repo, "--base-ref", "origin/main") == 1
    assert "append-only" in capsys.readouterr().err


def test_git_show_missing_ref_returns_none() -> None:
    assert cli._git_show("refs/heads/does-not-exist-anywhere", "logs/unverified.yaml") is None


def test_packaged_dataset_is_valid() -> None:
    assert cli.main(["--root", str(ROOT), "--today", "2026-11-06"]) == 0
