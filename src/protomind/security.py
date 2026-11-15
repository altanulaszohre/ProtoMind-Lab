"""Redacted allowlist-based publication audit."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from .storage import ROOT

ALLOWED_TOP = {"README.md", "LICENSE", "pyproject.toml", ".gitignore", ".env.example", "src", "configs", "scripts", "tests", "docs", ".githooks", "web", "assets", "recordings", "desktop", "Launch ProtoMind Lab.command", "publication-manifest.json"}
ALLOWED_SUFFIX = {".py", ".sh", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".ts", ".js", ".css", ".html", ".svg", ".swift", ".command"}
MAX_BYTES = 1_000_000
PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "token": re.compile(rb"(?:ghp_|github_pat_|hf_|sk-)[A-Za-z0-9_-]{20,}"),
    "credential_assignment": re.compile(rb"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-]{12,}"),
    "personal_path": re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/"),
}


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)


def policy(path: str, data: bytes) -> list[str]:
    parts = Path(path).parts
    issues = []
    if not parts or parts[0] not in ALLOWED_TOP:
        issues.append("outside publication allowlist")
    approved_binary = False
    if path.startswith("docs/images/") and Path(path).suffix in (".png", ".gif"):
        try:
            registry = json.loads((ROOT / "docs/images/manifest.json").read_text())["binary_sha256"]
            valid_magic = data.startswith(b"\x89PNG\r\n\x1a\n") if path.endswith(".png") else data.startswith((b"GIF87a", b"GIF89a"))
            approved_binary = valid_magic and registry.get(path) == hashlib.sha256(data).hexdigest() and len(data) <= 6_000_000
        except (OSError, ValueError, KeyError): pass
        if not approved_binary: issues.append("unregistered or invalid documentation media")
    if path.startswith("assets/") and Path(path).suffix in (".png", ".icns"):
        try:
            registry = json.loads((ROOT / "assets/manifest.json").read_text())["binary_sha256"]
            magic = b"\x89PNG\r\n\x1a\n" if path.endswith(".png") else b"icns"
            approved_binary = data.startswith(magic) and registry.get(path) == hashlib.sha256(data).hexdigest() and len(data) <= 4_000_000
        except (OSError, ValueError, KeyError): pass
        if not approved_binary: issues.append("unregistered or invalid public asset")
    if path == "recordings/predator-pressure.json.gz":
        try:
            manifest = json.loads((ROOT / "recordings/manifest.json").read_text())
            if len(data) > 200_000: raise ValueError("recording too large")
            approved_binary = hashlib.sha256(data).hexdigest() == manifest["sha256"]
            # Scan decompressed public recording content for private material too.
            decoded = gzip.decompress(data)
            if len(decoded) > 5_000_000: raise ValueError("recording expands beyond limit")
            json.loads(decoded)
            for category, regex in PATTERNS.items():
                if regex.search(decoded): issues.append(category)
        except (OSError, ValueError, KeyError): approved_binary = False
        if not approved_binary: issues.append("unverified public recording")
    if not approved_binary and Path(path).suffix not in ALLOWED_SUFFIX and Path(path).name not in {".gitignore", ".env.example", "LICENSE", "pre-commit", "pre-push"}:
        issues.append("disallowed file type")
    if len(data) > MAX_BYTES and not approved_binary:
        issues.append("large file")
    if b"\0" in data[:4096] and not approved_binary:
        issues.append("binary content")
    for category, regex in PATTERNS.items():
        if regex.search(data):
            issues.append(category)
    return issues


def audit(scope: str = "all") -> tuple[list[tuple[str, str, str]], bool]:
    findings: list[tuple[str, str, str]] = []
    has_git = git("rev-parse", "--is-inside-work-tree").returncode == 0
    # Audit current publishable source even when no repository has been initialized.
    for base, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {".venv", ".cache", "models", "runtime", "data", "experiments", "logs", "tmp", ".git", "__pycache__", "node_modules"} and not d.endswith(".app") and not (Path(base) / d).is_symlink()]
        for name in files:
            if name == ".DS_Store":
                continue  # ignored OS metadata; tracked copies are audited below
            file = Path(base) / name
            rel = file.relative_to(ROOT).as_posix()
            if file.is_symlink():
                findings.append(("working", rel, "symlink"))
                continue
            for issue in policy(rel, file.read_bytes()):
                findings.append(("working", rel, issue))
    if not has_git:
        return findings, False
    for label, args in (("tracked", ("ls-files", "-z")), ("staged", ("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"))):
        if scope == "staged" and label == "tracked": continue
        for raw in git(*args).stdout.split(b"\0"):
            if not raw: continue
            path = raw.decode(errors="replace")
            if label == "staged":
                blob = git("show", f":{path}")
                data = blob.stdout if blob.returncode == 0 else b""
            else:
                file = ROOT / path
                data = file.read_bytes() if file.is_file() and not file.is_symlink() else b""
            for issue in policy(path, data):
                findings.append((label, path, issue))
    if scope == "all":
        commits = git("rev-list", "--all").stdout.splitlines()
        for commit in commits:
            tree = git("ls-tree", "-r", "-z", commit.decode()).stdout
            for entry in tree.split(b"\0"):
                if not entry: continue
                meta, raw_path = entry.split(b"\t", 1)
                path = raw_path.decode(errors="replace")
                blob_id = meta.split()[-1].decode()
                size_raw = git("cat-file", "-s", blob_id).stdout.strip()
                if size_raw.isdigit() and int(size_raw) > 6_000_000:
                    findings.append(("history", path, "large file"))
                    continue
                data = git("cat-file", "blob", blob_id).stdout
                for issue in policy(path, data):
                    findings.append(("history", path, issue))
    return sorted(set(findings)), True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true", help="Audit a source distribution without requiring Git history")
    parser.add_argument("--scope", choices=["all", "staged"], default="all")
    args = parser.parse_args()
    findings, has_git = audit(args.scope)
    for label, path, issue in findings:
        print(f"{label}: {path}: {issue} [value redacted]")
    if not has_git:
        print("Git metadata absent: source files audited; staged files and history are not available")
    if not findings:
        print("No findings in inspected files")
    raise SystemExit(1 if findings or (not has_git and not args.source_only) else 0)


if __name__ == "__main__":
    main()
