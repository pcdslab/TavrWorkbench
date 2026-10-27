"""Data-map parsing and per-case asset discovery (no Slicer imports)."""
import json
import os

from .constants import (IMAGE_EXTENSIONS, MARKUP_EXTENSIONS, MARKUP_GROUP_KEYS, MEASUREMENT_KEY_TO_LABEL,
                        MODEL_EXTENSIONS, PLANES)


def is_file(path):
    return isinstance(path, str) and bool(path) and os.path.exists(path)


def is_image_path(path):
    return isinstance(path, str) and path.endswith(IMAGE_EXTENSIONS)


def case_id_of(sample, idx):
    return str(sample.get("case_id", idx))


def _resolve(path, base_dir):
    """Absolute paths are used as-is; relative ones are relative to the data-map file's folder."""
    if not isinstance(path, str) or not path:
        return path
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))


def resolve_sample_paths(sample, base_dir):
    """Copy of `sample` with every file path made absolute, so a dataset folder can be moved anywhere."""
    out = dict(sample)
    for key in ("image", "label"):
        if key in out:
            out[key] = _resolve(out[key], base_dir)
    for group in MARKUP_GROUP_KEYS:
        if isinstance(out.get(group), dict):
            out[group] = {name: _resolve(p, base_dir) for name, p in out[group].items()}
    return out


def read_data_map(path):
    """Return (usable_samples, n_skipped). A sample is usable when its 'image' exists and is a volume.
    Paths in the map may be absolute or relative to the map file (portable datasets)."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        samples = data
    elif "samples" in data:
        samples = data["samples"]
    else:
        samples = sum([data.get(k, []) for k in ("training", "validation", "testing")], [])

    base_dir = os.path.dirname(os.path.abspath(path))
    usable, skipped = [], 0
    for s in samples:
        if isinstance(s, dict):
            s = resolve_sample_paths(s, base_dir)
        image = s.get("image", "") if isinstance(s, dict) else ""
        if is_image_path(image) and is_file(image):
            usable.append(s)
        else:
            skipped += 1
    return usable, skipped


def collect_case_assets(sample):
    """Return (markups, models): dicts of 'group.name' -> path, for files that exist on disk."""
    markups, models = {}, {}
    for group_key in MARKUP_GROUP_KEYS:
        group = sample.get(group_key)
        if not isinstance(group, dict):
            continue
        for name, path in group.items():
            if not is_file(path):
                continue
            full_key = f"{group_key}.{name}"
            if path.endswith(MODEL_EXTENSIONS):
                models[full_key] = path
            elif path.endswith(MARKUP_EXTENSIONS):
                markups[full_key] = path
    return markups, models


def has_contours(sample):
    contours = sample.get("contours") or {}
    return isinstance(contours, dict) and any(is_file(contours.get(p)) for p in PLANES)


def has_measurements(sample):
    markups, _ = collect_case_assets(sample)
    return bool(markups)


def measurement_rating_keys(samples):
    """Keys of every measurement markup present in the data map, in a stable display order."""
    keys = set()
    for s in samples:
        markups, _ = collect_case_assets(s)
        keys.update(markups)
    ordered = [k for k in MEASUREMENT_KEY_TO_LABEL if k in keys]
    ordered += sorted(k for k in keys if k not in MEASUREMENT_KEY_TO_LABEL)
    return ordered
