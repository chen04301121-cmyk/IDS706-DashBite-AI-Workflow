"""Read-only artifact/handoff inspection, optionally waiting for live output."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from pipeline.paths import data_root


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inside(root: Path, relative: str) -> Path:
    """Reject absolute paths, traversal and symlinks outside the selected root."""
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, f'unsafe path: {relative}')
    path = root / rel
    require(path.resolve().is_relative_to(root.resolve()), f'path escapes root: {relative}')
    return path


def artifact_files(root):
    files = []
    for path in sorted(root.rglob('*')):
        inside(root, path.relative_to(root).as_posix())
        if path.is_file() and path != root / 'smoke-manifest.json':
            files.append(path)
    return files


def read_manifest(root, name='smoke-manifest.json'):
    path = inside(root, name)
    require(path.is_file(), 'missing or empty manifest')
    value = json.loads(path.read_text())
    require(isinstance(value, dict) and value.get('version') == 1,
            'invalid manifest version')
    files = value.get('files')
    require(isinstance(files, dict) and bool(files), 'missing or empty manifest')
    for relative, digest in files.items():
        inside(root, relative)
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest),
                f'invalid checksum: {relative}')
    return files


def read_frames(root, pattern, columns):
    files = sorted(root.glob(pattern))
    require(files, f'waiting for {pattern} under {root}')
    frames = []
    for path in files:
        inside(root, path.relative_to(root).as_posix())
        frame = pd.read_csv(path, dtype={'order_id': str, 'checkpoint_id': str})
        require(set(columns) <= set(frame.columns), f'missing columns in {path}: {columns}')
        frames.append(frame)
    frame = pd.concat(frames, ignore_index=True)
    require(not frame.empty, f'empty rows: {pattern}')
    return files, frame


def validate(root):
    raw_files, raw = read_frames(root, 'raw/orders_*.csv', ['order_id'])
    feature_files, features = read_frames(root, 'features/features_*.csv', ['order_id', 'hour', 'is_peak'])
    prediction_files, predictions = read_frames(root, 'predictions/predictions_*.csv',
        ['order_id', 'late_probability', 'predicted_late', 'checkpoint_id'])
    require(features.order_id.notna().all() and set(features.order_id) <= set(raw.order_id),
            'feature IDs must come from raw orders')
    require(predictions.order_id.notna().all() and predictions.order_id.is_unique
            and set(predictions.order_id) <= set(features.order_id),
            'invalid predictions: duplicate, missing or unlinked order IDs')
    probability = pd.to_numeric(predictions.late_probability, errors='coerce')
    require(np.isfinite(probability).all() and probability.between(0, 1).all(),
            'invalid predictions: probability must be finite and in [0,1]')
    require(predictions.predicted_late.isin([0, 1]).all(), 'invalid predictions: nonbinary labels')
    require(predictions.checkpoint_id.notna().all(), 'invalid predictions: missing checkpoint IDs')
    checkpoints = sorted(root.glob('models/checkpoint_*.joblib'))
    require(checkpoints, 'waiting for checkpoints')
    checkpoint_ids = set()
    for path in checkpoints:
        inside(root, path.relative_to(root).as_posix())
        checkpoint_id = path.stem.removeprefix('checkpoint_')
        try:
            bundle = joblib.load(path)
        except Exception as exc:
            raise ValueError(f'cannot load checkpoint {path}: {exc}') from exc
        require(isinstance(bundle, dict) and bundle.get('checkpoint_id') == checkpoint_id,
                f'checkpoint bundle ID mismatch: {path}')
        require(callable(getattr(bundle.get('model'), 'predict_proba', None)),
                f'checkpoint lacks callable model: {path}')
        metrics_path = inside(root, f'models/metrics_{checkpoint_id}.json')
        metrics = json.loads(metrics_path.read_text())
        require(metrics.get('checkpoint_id') == checkpoint_id
                and isinstance(metrics.get('accuracy'), (int, float))
                and 0 <= metrics['accuracy'] <= 1
                and metrics.get('n_train', 0) > 0 and metrics.get('n_test', -1) >= 0,
                f'invalid metrics: {metrics_path}')
        checkpoint_ids.add(checkpoint_id)
    require(set(predictions.checkpoint_id) <= checkpoint_ids,
            'invalid predictions: referenced checkpoint missing')
    state_path = inside(root, 'models/train_state.json')
    state = json.loads(state_path.read_text())
    require(isinstance(state, dict), f'invalid training state: expected object in {state_path}')
    require(state.get('last_checkpoint') in {p.name for p in checkpoints},
            f"invalid training state: last_checkpoint={state.get('last_checkpoint')!r} "
            f"not in checkpoint snapshot ({len(checkpoints)} files)")
    count = state.get('labeled_rows_at_last_train')
    require(type(count) is int and 0 < count <= len(features),
            f'invalid training state: labeled_rows_at_last_train={count!r}; '
            f'feature snapshot rows={len(features)} (expected integer in 1..{len(features)})')
    _, quality = read_frames(root, 'quality/batch_quality.csv', ['batch_file', 'rows_in', 'rows_out'])
    require((quality.rows_out >= 0).all() and quality.rows_out.sum() > 0
            and (quality.rows_in >= quality.rows_out).all(), 'invalid quality row counts')
    for path in feature_files:
        raw_name = path.stem.removeprefix('features_') + '.csv'
        marker = inside(root, f'features/.done_{raw_name}')
        require(marker.is_file() and marker.read_text() == raw_name, f'missing/invalid marker: {marker}')
        require(raw_name in set(quality.batch_file), f'missing quality record: {raw_name}')
    return {'raw': (raw_files, raw), 'features': (feature_files, features),
            'predictions': (prediction_files, predictions), 'quality': ([root / 'quality/batch_quality.csv'], quality),
            'checkpoints': checkpoints}


def validate_new(root, result, manifest):
    counts = {}
    for key in ('raw', 'features', 'checkpoints', 'predictions'):
        files = result[key] if key == 'checkpoints' else result[key][0]
        new = [p for p in files if p.relative_to(root).as_posix() not in manifest]
        require(new, f'waiting for new {key} since manifest')
        counts[key] = len(new)
    old_ids = set()
    baseline = [rel for rel in manifest if rel.startswith('predictions/') and rel.endswith('.csv')]
    require(baseline, 'manifest has no baseline predictions')
    for rel in baseline:
        path = inside(root, rel)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest[rel],
                f'baseline prediction changed: {rel}')
        old_ids.update(pd.read_csv(path, dtype={'order_id': str}).order_id)
    new_files = [p for p in result['predictions'][0]
                 if p.relative_to(root).as_posix() not in manifest]
    new_rows = pd.concat([pd.read_csv(p, dtype={'order_id': str}) for p in new_files], ignore_index=True)
    new_rows = new_rows[~new_rows.order_id.isin(old_ids)]
    require(not new_rows.empty, 'waiting for new prediction order IDs since manifest')
    print(f'New files: {counts}; new prediction rows: {len(new_rows)}')
    print(new_rows.head(5).to_string(index=False))


def report(root, result):
    print(f'DATA_ROOT: {root}')
    for key in ('raw', 'features', 'predictions', 'quality'):
        files, rows = result[key]
        print(f'{key}: {len(files)} files, {len(rows)} rows; example: {files[0]}')
    print(f"checkpoints: {len(result['checkpoints'])}; example: {result['checkpoints'][0]}")
    print(result['predictions'][1].head(5).to_string(index=False))
    print('PASS: artifacts and handoffs verified')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', type=float, default=0)
    parser.add_argument('--new-since')
    args = parser.parse_args(argv)
    if not np.isfinite(args.wait) or args.wait < 0:
        parser.error('--wait must be finite and nonnegative')
    root = data_root().resolve()
    print(f'DATA_ROOT: {root}', flush=True)
    deadline = time.monotonic() + args.wait
    try:
        manifest = read_manifest(root, args.new_since) if args.new_since else None
    except Exception as exc:
        print(f'FAIL: {exc}', flush=True)
        return 1
    while True:
        try:
            result = validate(root)
            if manifest is not None:
                validate_new(root, result, manifest)
            report(root, result)
            if manifest is not None:
                print('PASS: new predictions appeared after restart')
            return 0
        except Exception as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                prefix = f'timed out after {args.wait:g}s: ' if args.wait else ''
                print(f'FAIL: {prefix}{exc}', flush=True)
                return 1
            print(f'Waiting: {exc} ({remaining:.1f}s left)', flush=True)
            time.sleep(min(2, remaining))


if __name__ == '__main__':
    raise SystemExit(main())
