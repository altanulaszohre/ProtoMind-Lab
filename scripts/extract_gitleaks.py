"""Extract only a regular gitleaks binary from a project-local release archive."""
from __future__ import annotations

import sys
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
archive = Path(sys.argv[1]).resolve()
if not archive.is_relative_to((root / "tmp").resolve()):
    raise ValueError("archive must be inside project tmp")
target = root / "runtime/gitleaks/gitleaks"
if target.is_symlink():
    raise ValueError("gitleaks target is a symlink")
with tarfile.open(archive, "r:gz") as source:
    members = source.getmembers()
    binary = next((m for m in members if m.name == "gitleaks" and m.isfile() and m.size < 50_000_000), None)
    if binary is None:
        raise ValueError("regular gitleaks binary absent")
    data = source.extractfile(binary)
    if data is None:
        raise ValueError("binary data absent")
    with target.open("wb") as out:
        while chunk := data.read(1024 * 1024): out.write(chunk)
target.chmod(0o755)
