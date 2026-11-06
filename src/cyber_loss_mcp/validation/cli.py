"""``cyber-loss-validate``: validate the dataset, its logs and its profiles.

Run from the repository root. With ``--base-ref``, each log is also compared with its
version on that git ref, to prove it was only appended to.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from . import document, paths
from .report import Issue, errors

LOG_FILES = ("logs/unverified.yaml", "logs/corrections.yaml")


def _git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "show", f"{ref}:{path}"],  # noqa: S607 - git from PATH
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def run(root: Path, today: dt.date, base_ref: str | None) -> list[Issue]:
    issues: list[Issue] = []
    for name in document.PROFILES:
        issues += document.load_profile(name)[1]

    incidents = Path(str(paths.INCIDENTS))
    for path in sorted(incidents.iterdir()):
        rel = f"incidents/{path.name}"
        if path.name == ".gitkeep":
            continue
        if path.suffix != ".yaml" or not path.is_file():
            issues.append(Issue(rel, "", "only .yaml incident records belong here"))
            continue
        issues += document.validate(path.read_text(encoding="utf-8"), rel, today)

    for rel in LOG_FILES:
        path = root / rel
        if not path.is_file():
            issues.append(Issue(rel, "", "log file is missing"))
            continue
        base = _git_show(base_ref, rel) if base_ref else None
        issues += document.validate(path.read_text(encoding="utf-8"), rel, today, base)
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cyber-loss-validate", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--base-ref", help="git ref the logs must only append to")
    parser.add_argument(
        "--today", type=dt.date.fromisoformat, default=dt.datetime.now(dt.UTC).date()
    )
    args = parser.parse_args(argv)
    issues = run(args.root, args.today, args.base_ref)
    for issue in issues:
        print(issue, file=sys.stderr)
    failed = errors(issues)
    count = len(list(Path(str(paths.INCIDENTS)).glob("*.yaml")))
    print(
        f"{count} incident records checked; {len(failed)} errors, "
        f"{len(issues) - len(failed)} warnings"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
