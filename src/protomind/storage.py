"""Project-local paths and storage diagnostics."""
from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIRS = ("models", "runtime", ".venv", ".cache", "data", "experiments", "logs", "tmp")
CACHE_ENV = {
    "HF_HOME": ".cache/huggingface", "HUGGINGFACE_HUB_CACHE": ".cache/huggingface/hub",
    "XDG_CACHE_HOME": ".cache/xdg", "PIP_CACHE_DIR": ".cache/pip",
    "TMPDIR": "tmp", "TEMP": "tmp", "TMP": "tmp",
    "PYTHONPYCACHEPREFIX": ".cache/pycache",
}


def configure_local_environment() -> None:
    for directory in LOCAL_DIRS:
        if (ROOT / directory).is_symlink():
            raise ValueError(f"managed directory is a symlink: {directory}")
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    for key, relative in CACHE_ENV.items():
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f"cache path escapes project root: {key}")
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def local_path(relative: str) -> Path:
    candidate = (ROOT / relative).resolve()
    if not candidate.is_relative_to(ROOT.resolve()):
        raise ValueError("path escapes project root")
    return candidate


def external_paths() -> list[str]:
    findings = [key for key in CACHE_ENV if not Path(os.environ.get(key, str(ROOT))).resolve().is_relative_to(ROOT.resolve())]
    for directory in ("models", "runtime", ".cache", "data", "experiments", "logs", "tmp"):
        base = ROOT / directory
        for root, dirs, files in os.walk(base, followlinks=False):
            for name in dirs + files:
                path = Path(root) / name
                if path.is_symlink() and not path.resolve().is_relative_to(ROOT.resolve()):
                    findings.append(str(path.relative_to(ROOT)))
    return findings


def owned_bytes() -> int:
    total = 0
    for base, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            path = Path(base) / name
            if not path.is_symlink():
                total += path.stat().st_size
    return total
