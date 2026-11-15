"""Extract the pinned llama.cpp archive without traversal or external symlink targets."""
from __future__ import annotations

import os
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "runtime"


def extract(archive: Path) -> None:
    if not archive.resolve().is_relative_to((ROOT / "tmp").resolve()):
        raise ValueError("archive must be in project tmp")
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if len(members) > 200 or sum(m.size for m in members) > 300_000_000:
            raise ValueError("unexpected archive size")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != "llama-b12088":
                raise ValueError("unsafe archive path")
            if not (member.isdir() or member.isfile() or member.issym()):
                raise ValueError("unsupported archive entry")
            target = DEST.joinpath(*name.parts)
            if target.is_symlink() or not target.parent.resolve().is_relative_to(DEST.resolve()):
                raise ValueError("external extraction path")
            if member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or ".." in link.parts or not (target.parent / member.linkname).resolve().is_relative_to((DEST / "llama-b12088").resolve()):
                    raise ValueError("unsafe archive symlink")
        for member in members:
            if member.issym(): continue
            target = DEST / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                data = source.extractfile(member)
                if data is None: raise ValueError("missing archive data")
                with target.open("wb") as out:
                    while chunk := data.read(1024 * 1024): out.write(chunk)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
        for member in members:
            if member.issym():
                target = DEST / member.name
                if target.exists() or target.is_symlink(): target.unlink()
                os.symlink(member.linkname, target)
    if not (DEST / "llama-b12088/llama-server").is_file():
        raise ValueError("llama-server absent from runtime archive")


if __name__ == "__main__":
    extract(Path(sys.argv[1]))
