#!/usr/bin/env python3
"""Verify the public source inventory and local documentation media."""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'publication-manifest.json'
IGNORED = {'.git', '.venv', '.cache', 'node_modules', '__pycache__', 'models', 'runtime', 'data', 'experiments', 'logs', 'tmp'}

def files():
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT)
        if any(part in IGNORED or part.endswith('.app') for part in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'Symlink in source: {rel}')
        if path.is_file() and rel.as_posix() != 'publication-manifest.json':
            yield rel.as_posix(), path

def main():
    manifest = json.loads(MANIFEST.read_text())
    expected = manifest['files']
    actual = {name: path for name, path in files()}
    if set(actual) != set(expected):
        raise ValueError(f'Inventory differs: missing={sorted(set(expected)-set(actual))}; extra={sorted(set(actual)-set(expected))}')
    for name, path in actual.items():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError(f'Hash mismatch: {name}')
        if name.endswith(('.gguf', '.safetensors', '.db', '.sqlite', '.pem', '.key', '.zip', '.mp4')):
            raise ValueError(f'Forbidden file: {name}')
        if name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(f'Invalid PNG: {name}')
        if name.endswith('.gif') and not data.startswith((b'GIF87a', b'GIF89a')):
            raise ValueError(f'Invalid GIF: {name}')
        if name.endswith('.md'):
            text = data.decode('utf-8')
            for target in re.findall(r'!?\[[^]]*\]\(([^)]+)\)|<img\s+[^>]*src="([^"]+)"', text):
                ref = next((value for value in target if value), '')
                if ref.startswith(('https://', 'http://', '#', 'mailto:')):
                    continue
                if ref.startswith(('/', 'file:')) or not (path.parent / ref.split('#')[0]).is_file():
                    raise ValueError(f'Broken or absolute link: {name}: {ref}')
            if re.search(r'[\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc]|/(?:Users|home)/[A-Za-z0-9_.-]+/', text):
                raise ValueError(f'Non-English or personal path: {name}')
    print(f'Publication inventory verified: {len(actual)} files, {sum(p.stat().st_size for p in actual.values())} bytes')

if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
