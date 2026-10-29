"""Shared constants for TavrWorkbench (no Slicer imports, safe to unit-test)."""

# ---------------------------------------------------------------------------
# Review ratings
# ---------------------------------------------------------------------------
RATING_ACCEPT = "accepted"
RATING_FLAG = "flagged"
RATING_NONE = ""

# Reviews saved with the old 3-option scheme are mapped onto the 2-option one when read.
LEGACY_RATING_MAP = {
    "acceptable": RATING_ACCEPT,
    "minor": RATING_FLAG,
    "not_acceptable": RATING_FLAG,
}

RATING_TO_STR = {
    RATING_ACCEPT: "✓ Approved",
    RATING_FLAG: "⚑ Flagged for review",
    RATING_NONE: "",
}
RATING_TO_MARK = {RATING_ACCEPT: "✓", RATING_FLAG: "⚑"}
PENDING_MARK = "·"
NOT_APPLICABLE_MARK = "–"


def normalize_rating(value):
    value = LEGACY_RATING_MAP.get(value, value)
    return value if value in (RATING_ACCEPT, RATING_FLAG) else RATING_NONE


def normalize_review(review):
    """Return a clean review dict (or None). Older review.json files lack 'measurements_overall'."""
    if not isinstance(review, dict):
        return None
    out = dict(review)
    out["overall"] = normalize_rating(review.get("overall", RATING_NONE))
    out["measurements_overall"] = normalize_rating(review.get("measurements_overall", RATING_NONE))
    for key in ("segmentation", "measurements"):
        out[key] = {k: normalize_rating(v) for k, v in (review.get(key) or {}).items()}
    out["comment"] = review.get("comment", "") or ""
    return out


# ---------------------------------------------------------------------------
# Review modes
# ---------------------------------------------------------------------------
MODE_SEGMENTATION = "segmentation"
MODE_MEASUREMENTS = "measurements"
MODES = [MODE_SEGMENTATION, MODE_MEASUREMENTS]

# Shift+<letter> is identical on Windows, macOS and Linux and doesn't collide with Slicer's
# Ctrl+<n> layout shortcuts. Each shortcut acts on the decision of the active mode.
SHORTCUT_ACCEPT = "Shift+A"
SHORTCUT_FLAG = "Shift+F"

# ---------------------------------------------------------------------------
# Data-map content
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = (".nii", ".nii.gz", ".nrrd")
MODEL_EXTENSIONS = (".vtp",)
MARKUP_EXTENSIONS = (".mrk.json", ".json")

SEGMENTATION_LABELS = [
    "Aorta",
    "Aortic Root",
    "Left Ventricle",
    "Coronaries",
    "Thoracic Aorta",
]

MEASUREMENT_KEY_TO_LABEL = {
    "hinge_points.LCC": "Hinge Point LCC",
    "hinge_points.RCC": "Hinge Point RCC",
    "hinge_points.NCC": "Hinge Point NCC",
    "contours.annulus": "Annulus Contour",
    "contours.sov": "SOV Contour",
    "contours.stj": "STJ Contour",
    "max_diameters.annulus": "Annulus Max Diameter",
    "max_diameters.sov": "SOV Max Diameter",
    "max_diameters.stj": "STJ Max Diameter",
    "min_diameters.annulus": "Annulus Min Diameter",
    "min_diameters.sov": "SOV Min Diameter",
    "min_diameters.stj": "STJ Min Diameter",
    "heights.stj": "STJ Height",
    "heights.lch": "LCH Height",
    "heights.rch": "RCH Height",
    "centerline.points": "Centerline Points",
}
ALL_MEASUREMENT_COLUMNS = list(MEASUREMENT_KEY_TO_LABEL.values())

# Sample keys that hold markup / model paths
MARKUP_GROUP_KEYS = ["hinge_points", "contours", "max_diameters", "min_diameters", "heights", "centerline"]
# Groups the measurement editor builds itself (everything else is loaded view-only)
EDITOR_GROUP_KEYS = ("contours", "max_diameters", "min_diameters", "heights")

# ---------------------------------------------------------------------------
# Output folder
# ---------------------------------------------------------------------------
SEG_STATUS_FILE = "review_status.json"         # segmentation review progress
MEAS_STATUS_FILE = "correction_status.json"    # measurement review / correction progress
ANNOTATIONS_CSV = "annotations.csv"            # one row per case: all Approve/Flag ratings
MEASUREMENTS_CSV = "corrected_measurements.csv"  # one row per case + plane: contour metrics
CASE_REVIEW_FILE = "review.json"
CASE_MASK_FILE = "segmentation.seg.nrrd"
LOG_FILE = "tavr_workbench.log"

ANNOTATION_COLUMNS = (["case_id", "file", "comment", "mask_path", "mask_status", "overall"]
                      + SEGMENTATION_LABELS + ["measurements_overall"] + ALL_MEASUREMENT_COLUMNS
                      + ["saved_at"])
MEASUREMENT_COLUMNS = ["case_id", "plane", "edited", "area_mm2", "perimeter_mm", "max_d_mm", "min_d_mm",
                       "mean_d_mm", "eccentricity", "n_control_pts", "saved_at"]

MASK_STATUS_TEXT = {0: "No mask found", 1: "Cannot load mask", 2: "Mask loaded, no edits", 3: "Mask edited"}

# ---------------------------------------------------------------------------
# Measurement editor
# ---------------------------------------------------------------------------
CONTOUR_FILE_SUFFIX = {"curve": "contour", "max": "max_d", "min": "min_d"}
PLANES = ["annulus", "sov", "stj"]
PLANE_COLORS = {"annulus": (1.0, 0.8, 0.0), "sov": (0.2, 0.9, 0.4), "stj": (0.3, 0.7, 1.0)}
HEIGHTS = ["stj", "lch", "rch"]
HEIGHT_NAMES = {"stj": "STJ height", "lch": "Left coronary (LCH)", "rch": "Right coronary (RCH)"}
HEIGHT_COLORS = {"stj": (1.0, 0.3, 0.9), "lch": (0.2, 1.0, 1.0), "rch": (1.0, 0.5, 0.1)}
CONTOUR_FOV = 70.0  # mm, contour-plane view
HEIGHT_FOV = 90.0   # mm, long-axis height views
MEAS_SEGMENTATION_OPACITY_3D = 0.25  # 3D segmentation opacity in Measurements mode ("Segmentation" box)
# One radio group: contours first, then heights (selection key -> height key)
SELECTIONS = ["annulus", "sov", "stj", "stj_h", "lch", "rch"]
SELECTION_LABELS = {"annulus": "ANNULUS", "sov": "SOV", "stj": "STJ",
                    "stj_h": "STJ-H", "lch": "LCH", "rch": "RCH"}
HEIGHT_SEL = {"stj_h": "stj", "lch": "lch", "rch": "rch"}
