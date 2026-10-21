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


def read_data_map(path):
    """Return (usable_samples, n_skipped). A sample is usable when its 'image' exists and is a volume."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        samples = data
    elif "samples" in data:
        samples = data["samples"]
    else:
        samples = sum([data.get(k, []) for k in ("training", "validation", "testing")], [])

    usable, skipped = [], 0
    for s in samples:
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
