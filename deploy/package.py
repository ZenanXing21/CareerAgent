"""Create a source-only deployment bundle without local data or credentials."""

from __future__ import annotations

import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tmp" / "career-agent-deploy.tar.gz"
SOURCES = (
    "deploy/Dockerfile",
    "pyproject.toml",
    "README.md",
    "career_agent",
    "vendor/liepin-cil/pyproject.toml",
    "vendor/liepin-cil/README.md",
    "vendor/liepin-cil/liepin_cli",
)


def include(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if any(part in {"__pycache__", ".venv", ".git"} for part in Path(info.name).parts):
        return None
    if info.name.endswith((".pyc", ".pyo")):
        return None
    return info


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    with tarfile.open(OUTPUT, "w:gz") as archive:
        for source in SOURCES:
            archive.add(ROOT / source, arcname=source, filter=include)
    print(f"Created {OUTPUT.name}: {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
