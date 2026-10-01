"""Save a stopped-writer baseline, or verify it before writers restart.

The caller must stop writers: an artifact reader cannot certify process state.
"""
import argparse
import hashlib
import json

from pipeline.paths import data_root
from scripts.check_artifacts import artifact_files, inside, read_manifest, report, require, validate


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {p.relative_to(root).as_posix(): checksum(p) for p in artifact_files(root)}


def save(root):
    path = inside(root, 'smoke-manifest.json')
    require(not path.exists(), 'manifest already exists')
    before = snapshot(root)
    result = validate(root)
    after = snapshot(root)
    require(before == after and bool(after), 'artifacts changed during validation; stop writers before save')
    report(root, result)
    # Exclusive creation preserves the original baseline even on concurrent saves.
    with path.open('x') as handle:
        json.dump({'version': 1, 'files': after}, handle, indent=2)
    print(f'PASS: saved {len(after)} artifact checksums to {path}')


def verify(root):
    files = read_manifest(root)
    for relative, expected in files.items():
        path = inside(root, relative)
        require(path.is_file(), f'saved artifact missing: {relative}')
        require(checksum(path) == expected, f'checksum changed: {relative}')
        print(f'unchanged: {relative}')
    print(f'PASS: {len(files)} original files survived container recreation unchanged')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['save', 'verify'])
    args = parser.parse_args(argv)
    root = data_root().resolve()
    print(f'DATA_ROOT: {root}')
    try:
        (save if args.action == 'save' else verify)(root)
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
