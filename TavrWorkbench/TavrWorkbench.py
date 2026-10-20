# TavrWorkbench.py
import csv
import json
import logging
import os
from datetime import datetime

import vtk
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import ctk
import qt
import SegmentStatistics

# Suppress VTK warnings globally to prevent console flooding and UI freezing
vtk.vtkObject.GlobalWarningDisplayOff()

try:
    import numpy as np
except:
    slicer.util.pip_install('numpy')
    import numpy as np

import warnings
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Review constants
# ---------------------------------------------------------------------------
RATING_ACCEPT = "accepted"
RATING_FLAG = "flagged"
RATING_NONE = ""

# Reviews/status saved with the old 3-option scheme are mapped onto the 2-option one when read.
LEGACY_RATING_MAP = {
    "acceptable": RATING_ACCEPT,
    "minor": RATING_FLAG,
    "not_acceptable": RATING_FLAG,
}


def normalize_rating(value):
    value = LEGACY_RATING_MAP.get(value, value)
    return value if value in (RATING_ACCEPT, RATING_FLAG) else RATING_NONE


def normalize_review(review):
    if not isinstance(review, dict):
        return None
    out = dict(review)
    out["overall"] = normalize_rating(review.get("overall", RATING_NONE))
    for key in ("segmentation", "measurements"):
        out[key] = {k: normalize_rating(v) for k, v in (review.get(key) or {}).items()}
    out.setdefault("comment", "")
    return out

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

# Group keys in a manifest sample that hold markup / model paths
MARKUP_GROUP_KEYS = ["hinge_points", "contours", "max_diameters", "min_diameters", "heights", "centerline"]
MODEL_EXTENSIONS = ('.vtp',)

# Keyboard shortcuts for the overall decision. Shift+<letter> is identical on Windows, macOS
# and Linux (unlike Ctrl/Alt/Meta, which are remapped per platform) and doesn't collide with
# Slicer's Ctrl+<n> layout shortcuts. Change here if you prefer other keys.
SHORTCUT_ACCEPT = "Shift+A"   # A for Approve
SHORTCUT_FLAG = "Shift+F"

# Output-folder file names
STATUS_FILE = "review_status.json"
CSV_FILE = "annotations.csv"
CASE_REVIEW_FILE = "review.json"
CASE_MASK_FILE = "segmentation.seg.nrrd"

RATING_TO_STR = {
    RATING_ACCEPT: "✓ Approved",
    RATING_FLAG: "⚑ Flagged for review",
    RATING_NONE: "",
}
RATING_TO_MARK = {
    RATING_ACCEPT: "✓",
    RATING_FLAG: "⚑",
}


class TavrWorkbench(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("TavrWorkbench")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []
        self.parent.contributors = ["Mohammed Khubaib (Saeed Lab: Florida International University)"]
        self.parent.helpText = _("""
        A 3D Slicer extension for fast, structured review of TAVR CT segmentations and measurements.
        See more information in <a href="https://github.com/organization/projectname#TavrWorkbench">module documentation</a>.
        """)
        self.parent.acknowledgementText = _("""
        This 3D Slicer module was developed by <a href="https://github.com/Mohammed-Khubaib">Mohammed Khubaib</a>, M.S. Computer Engineering, Florida International University, as part of the <a href="https://pcdslab.github.io/">Saeed Lab</a> under the supervision of <a href="https://pcdslab.github.io/team/Fahad-Saeed">Dr. Fahad Saeed</a> and <a href="https://www.cis.fiu.edu/faculty-staff/kaoutar-ben-ahmed/">Dr. Kaoutar Ben Ahmed</a>.""")

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#


def registerSampleData():
    """Add data sets to Sample Data module."""
    import SampleData

    iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")

    SampleData.SampleDataLogic.registerCustomSampleDataCategory("TavrWorkbench", title=_("TavrWorkbench"))

    # TODO: replace these placeholder sample data entries with real sample datasets for TavrWorkbench,
    # or remove this function (and the startupCompleted connection above) entirely.

    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        category="TavrWorkbench",
        sampleName="TavrWorkbench1",
        thumbnailFileName=os.path.join(iconsPath, "TavrWorkbench1.png"),
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        fileNames="TavrWorkbench1.nrrd",
        checksums="SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        nodeNames="TavrWorkbench1",
    )

    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        category="TavrWorkbench",
        sampleName="TavrWorkbench2",
        thumbnailFileName=os.path.join(iconsPath, "TavrWorkbench2.png"),
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        fileNames="TavrWorkbench2.nrrd",
        checksums="SHA256:1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        nodeNames="TavrWorkbench2",
    )


class TavrWorkbenchWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

        # ---- Current-case nodes ----
        self.volume_node = None
        self.segmentation_node = None
        self.pointListNode = None
        self.window_level = None
        self.segment_visiblity_states = {}
        self.loaded_markup_nodes = []
        self.loaded_model_nodes = []
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self.centerline_points_world = {}
        self.centerline_arclength = {}

        # ---- Case list / progress tracking (data-map + output folder) ----
        self.samples = []
        self.current_index = -1
        self.n_files = 0
        self.status = {}              # case_id -> {"overall", "time", "mask_edited"}
        self.mask_status = {}         # case_id -> 0..3 (see _numerical_status_to_str)
        self._case_loaded = False
        self._logger_handler = None

        # ---- Review state ----
        self.overall_button_group = None
        self.seg_button_groups = {}
        self.meas_button_groups = {}
        self.case_reviews = {}        # in-memory cache, index -> review dict
        self.active_measurement_keys = []

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup(self):
        import qSlicerSegmentationsModuleWidgetsPythonQt
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(self.resourcePath('UI/TavrWorkbench.ui'))

        # ---- Input section: data map + output folder + case selector ----
        inputCollapsibleButton = ctk.ctkCollapsibleButton()
        inputCollapsibleButton.text = "Input"
        self.layout.addWidget(inputCollapsibleButton)
        form = qt.QFormLayout(inputCollapsibleButton)

        self.mapEdit = ctk.ctkPathLineEdit()
        self.mapEdit.filters = ctk.ctkPathLineEdit.Files
        self.mapEdit.nameFilters = ["JSON files (*.json)"]
        self.mapEdit.settingKey = "TavrWorkbench/mapFile"
        self.mapEdit.setToolTip("Select the data-map .json (browse button on the right)")
        form.addRow("Data map (.json):", self.mapEdit)

        self.outEdit = ctk.ctkPathLineEdit()
        self.outEdit.filters = ctk.ctkPathLineEdit.Dirs
        self.outEdit.settingKey = "TavrWorkbench/outDir"
        self.outEdit.setToolTip("Reviews, edited masks, annotations.csv and progress are saved here")
        self.outEdit.connect("currentPathChanged(QString)", lambda _p: self.loadStatus())
        form.addRow("Output folder:", self.outEdit)

        self.loadListButton = qt.QPushButton("Load case list")
        self.loadListButton.connect("clicked()", self.loadList)
        form.addRow(self.loadListButton)

        self.caseCombo = qt.QComboBox()
        self.caseCombo.connect("activated(int)", lambda i: self.loadCase(i))
        form.addRow("Case:", self.caseCombo)

        self.nextUnreviewedButton = qt.QPushButton("Next unreviewed ⏭")
        self.nextUnreviewedButton.connect("clicked()", self.nextUnreviewed)
        form.addRow(self.nextUnreviewedButton)

        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self._createAlignmentWidget_()
        self._createCenterlineSlicingWidget_()
        self.logic = TavrWorkbenchLogic()

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)

        # Button connections
        self.ui.save_and_next.connect('clicked(bool)', self.save_and_next_clicked)
        self.ui.previous_case.connect('clicked(bool)', self.previous_case_clicked)
        self.ui.skip_case.connect('clicked(bool)', self.skip_case_clicked)
        self.ui.clear_overall.connect('clicked(bool)', self.clear_overall_clicked)
        self.ui.overwrite_mask.connect('clicked(bool)', self.overwrite_mask_clicked)

        self.overall_button_group = qt.QButtonGroup()
        self.overall_button_group.addButton(self.ui.radio_accept, 0)
        self.overall_button_group.addButton(self.ui.radio_flag, 1)

        self.ui.radio_accept.toggled.connect(lambda checked: self._onOverallToggled(RATING_ACCEPT, checked))
        self.ui.radio_flag.toggled.connect(lambda checked: self._onOverallToggled(RATING_FLAG, checked))
        self._setupOverallShortcuts()

        self._buildSegmentationReviewTable()
        self.ui.measReviewContainer.setVisible(False)

        self._createSegmentEditorWidget_()
        self._createMarkupWidget_()
        self._updateSummary()

    # ------------------------------------------------------------------
    # Output-folder helpers
    # ------------------------------------------------------------------
    def outDir(self):
        return str(self.outEdit.currentPath or "")

    @staticmethod
    def _safe_name(name):
        safe = "".join(c for c in str(name) if c.isalnum() or c in ('_', '-', '.')).strip()
        return safe or "unknown_case"

    def caseId(self, idx=None):
        idx = self.current_index if idx is None else idx
        if idx is None or idx < 0 or idx >= len(self.samples):
            return ""
        return str(self.samples[idx].get("case_id", idx))

    def caseDir(self, cid):
        return os.path.join(self.outDir(), self._safe_name(cid))

    def casePath(self, cid, filename):
        return os.path.join(self.caseDir(cid), filename)

    # ------------------------------------------------------------------
    # Progress tracking (review_status.json in the output folder)
    # ------------------------------------------------------------------
    def loadStatus(self):
        sp = os.path.join(self.outDir(), STATUS_FILE) if self.outDir() else ""
        self.status = {}
        if sp and os.path.exists(sp):
            try:
                with open(sp) as f:
                    self.status = json.load(f)
                for entry in self.status.values():
                    entry["overall"] = normalize_rating(entry.get("overall", RATING_NONE))
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not read {sp}: {e}")
        if self.samples:
            self.refreshCombo()
        self._updateSummary()

    def dumpStatus(self):
        if not self.outDir():
            return
        os.makedirs(self.outDir(), exist_ok=True)
        with open(os.path.join(self.outDir(), STATUS_FILE), "w") as f:
            json.dump(self.status, f, indent=2)

    def isReviewed(self, cid):
        return bool(self.status.get(str(cid), {}).get("overall"))

    def refreshCombo(self):
        self.caseCombo.blockSignals(True)
        self.caseCombo.clear()
        for s in self.samples:
            cid = str(s.get("case_id", ""))
            mark = RATING_TO_MARK.get(self.status.get(cid, {}).get("overall", ""), "·")
            self.caseCombo.addItem(f"{mark} {cid}")
        if 0 <= self.current_index < self.caseCombo.count:
            self.caseCombo.setCurrentIndex(self.current_index)
        self.caseCombo.blockSignals(False)

    def _updateSummary(self):
        total = len(self.samples)
        reviewed = sum(1 for s in self.samples if self.isReviewed(s.get("case_id", "")))
        self.ui.summaryTotal.setText(f"Total Samples in Dataset: {total}")
        self.ui.summaryReviewed.setText(f"Reviewed: {reviewed}")
        self.ui.summaryPending.setText(f"Pending: {total - reviewed}")
        if total and self.current_index >= 0:
            self.ui.status_checked.setText(f"Case {self.current_index + 1} / {total}  ({reviewed} reviewed)")
        else:
            self.ui.status_checked.setText("No case list loaded")

    # ------------------------------------------------------------------
    # Case list loading (data-map JSON)
    # ------------------------------------------------------------------
    def _is_valid_extension(self, path):
        return any(str(path).endswith(i) for i in [".nii", ".nii.gz", ".nrrd"])

    def _collect_case_assets(self, sample):
        """Return (markups, models) dicts of full_key -> path that exist on disk."""
        case_markups, case_models = {}, {}
        for group_key in MARKUP_GROUP_KEYS:
            group = sample.get(group_key)
            if not isinstance(group, dict):
                continue
            for name, path in group.items():
                full_key = f"{group_key}.{name}"
                if not isinstance(path, str) or not os.path.exists(path):
                    continue
                if path.endswith(MODEL_EXTENSIONS):
                    case_models[full_key] = path
                elif path.endswith(('.mrk.json', '.json')):
                    case_markups[full_key] = path
        return case_markups, case_models

    def loadList(self):
        mp = str(self.mapEdit.currentPath or "")
        if not mp or not os.path.isfile(mp):
            slicer.util.errorDisplay("Select the data-map .json file first.")
            return
        if not self.outDir():
            slicer.util.warningDisplay("No output folder selected yet - choose one before saving.")
        try:
            with open(mp) as f:
                data = json.load(f)
        except Exception as e:
            slicer.util.errorDisplay(f"Could not parse data-map JSON:\n{e}")
            return

        if isinstance(data, list):
            samples = data
        elif "samples" in data:
            samples = data["samples"]
        else:
            samples = sum([data.get(k, []) for k in ("training", "validation", "testing")], [])

        usable, skipped = [], 0
        all_meas_keys = set()
        for s in samples:
            image = s.get("image", "")
            if not (isinstance(image, str) and os.path.exists(image) and self._is_valid_extension(image)):
                skipped += 1
                continue
            usable.append(s)
            markups, _models = self._collect_case_assets(s)
            all_meas_keys.update(markups.keys())

        if not usable:
            slicer.util.errorDisplay("No usable cases found in this data map "
                                     "(every 'image' path is missing or has an unsupported extension).")
            return
        if skipped:
            print(f"[TavrWorkbench] Skipped {skipped} sample(s) with missing/unsupported image path.")

        self._clearCaseNodes()
        self.samples = usable
        self.n_files = len(usable)
        self.current_index = -1
        self._case_loaded = False
        self.case_reviews = {}
        self.mask_status = {}

        ordered_keys = [k for k in MEASUREMENT_KEY_TO_LABEL if k in all_meas_keys]
        for k in sorted(all_meas_keys):
            if k not in ordered_keys:
                ordered_keys.append(k)
        self._buildMeasurementReviewTable(ordered_keys)

        self._setupLogger(mp)
        self.loadStatus()
        self.refreshCombo()

        # Resume at the first unreviewed case (or the first case if all are done)
        start = 0
        for i, s in enumerate(self.samples):
            if not self.isReviewed(s.get("case_id", "")):
                start = i
                break
        msg = f"Loaded {self.n_files} cases"
        if skipped:
            msg += f" ({skipped} skipped: missing/unsupported image)"
        slicer.util.showStatusMessage(msg, 4000)
        self.loadCase(start)

    def _setupLogger(self, map_path):
        logger = logging.getLogger('TavrWorkbench')
        logger.setLevel(logging.DEBUG)
        if self._logger_handler is not None:
            logger.removeHandler(self._logger_handler)
            self._logger_handler = None
        log_dir = self.outDir() if self.outDir() and os.path.isdir(self.outDir()) else os.path.dirname(map_path)
        try:
            handler = logging.FileHandler(os.path.join(log_dir, 'tavr_workbench.log'))
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
            logger.addHandler(handler)
            self._logger_handler = handler
            logger.info(f'Loaded data map {map_path}')
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not create log file: {e}")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def step(self, d):
        if self.samples:
            self.loadCase(max(0, min(len(self.samples) - 1, self.current_index + d)))

    def nextUnreviewed(self):
        n = len(self.samples)
        if not n:
            return
        for k in range(1, n + 1):
            j = (self.current_index + k) % n
            if not self.isReviewed(self.samples[j].get("case_id", "")):
                return self.loadCase(j)
        slicer.util.infoDisplay("All cases have been reviewed.")

    def previous_case_clicked(self):
        if self.n_files == 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if self.current_index <= 0:
            slicer.util.warningDisplay("Already at the first case.")
            return
        self.loadCase(self.current_index - 1)

    def skip_case_clicked(self):
        """Move on to the next case without saving the current review."""
        if self.n_files == 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if self.current_index >= self.n_files - 1:
            slicer.util.warningDisplay("Already at the last case.")
            return
        self.loadCase(self.current_index + 1)

    def clear_overall_clicked(self):
        """Clear all radio buttons: Overall, Segmentation, and Measurement."""
        self._resetReviewUI()

    def loadCase(self, idx):
        if not self.samples:
            return
        idx = max(0, min(len(self.samples) - 1, int(idx)))
        if self._case_loaded and 0 <= self.current_index < len(self.samples):
            self._saveCurrentReview()   # keep in-memory so Prev/Next doesn't lose ratings
        self.current_index = idx
        self._loadCaseData()
        self._case_loaded = True
        self._restoreReview(idx)
        self.refreshCombo()
        self._updateSummary()

    # ------------------------------------------------------------------
    # Review tables
    # ------------------------------------------------------------------
    def _buildSegmentationReviewTable(self):
        container = self.ui.segReviewContainer
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        groupBox = qt.QGroupBox("Segmentation Review")
        grid = qt.QGridLayout(groupBox)

        grid.addWidget(qt.QLabel("<b>Label</b>"), 0, 0)
        grid.addWidget(qt.QLabel("<b>✓</b>"), 0, 1, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>⚑</b>"), 0, 2, qt.Qt.AlignCenter)

        for row_idx, label in enumerate(SEGMENTATION_LABELS, start=1):
            grid.addWidget(qt.QLabel(label), row_idx, 0)

            bg = qt.QButtonGroup()
            for col_idx, rating in enumerate([RATING_ACCEPT, RATING_FLAG], start=1):
                rb = qt.QRadioButton()
                bg.addButton(rb, col_idx)
                grid.addWidget(rb, row_idx, col_idx, qt.Qt.AlignCenter)
            self.seg_button_groups[label] = bg

        layout.addWidget(groupBox)

    def _buildMeasurementReviewTable(self, measurement_keys):
        container = self.ui.measReviewContainer
        old_layout = container.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
                sub = item.layout()
                if sub:
                    while sub.count():
                        si = sub.takeAt(0)
                        sw = si.widget()
                        if sw:
                            sw.deleteLater()
            old_layout.deleteLater()
        self.meas_button_groups.clear()

        if not measurement_keys:
            container.setVisible(False)
            self.active_measurement_keys = []
            return

        container.setVisible(True)
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        groupBox = qt.QGroupBox("Measurement Review")
        grid = qt.QGridLayout(groupBox)

        grid.addWidget(qt.QLabel("<b>Measurement</b>"), 0, 0)
        grid.addWidget(qt.QLabel("<b>✓</b>"), 0, 1, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>⚑</b>"), 0, 2, qt.Qt.AlignCenter)

        for row_idx, key in enumerate(measurement_keys, start=1):
            display = MEASUREMENT_KEY_TO_LABEL.get(key, key)
            grid.addWidget(qt.QLabel(display), row_idx, 0)

            bg = qt.QButtonGroup()
            for col_idx, rating in enumerate([RATING_ACCEPT, RATING_FLAG], start=1):
                rb = qt.QRadioButton()
                bg.addButton(rb, col_idx)
                grid.addWidget(rb, row_idx, col_idx, qt.Qt.AlignCenter)
            self.meas_button_groups[display] = bg

        layout.addWidget(groupBox)
        self.active_measurement_keys = measurement_keys

    def _setupOverallShortcuts(self):
        """Window-level shortcuts so the decision can be made while focus is in a slice/3D view."""
        self.ui.radio_accept.setText(f"✓ Approve ({SHORTCUT_ACCEPT})")
        self.ui.radio_flag.setText(f"⚑ Flag for review ({SHORTCUT_FLAG})")
        self._shortcuts = []
        for key, rating in ((SHORTCUT_ACCEPT, RATING_ACCEPT), (SHORTCUT_FLAG, RATING_FLAG)):
            sc = qt.QShortcut(qt.QKeySequence(key), slicer.util.mainWindow())
            sc.setContext(qt.Qt.WindowShortcut)
            sc.connect("activated()", lambda r=rating: self._onOverallShortcut(r))
            self._shortcuts.append(sc)

    def _onOverallShortcut(self, rating):
        # Only act while this module is the active one and a case is loaded
        if not self.parent.isEntered or self.current_index < 0:
            return
        button = self.ui.radio_accept if rating == RATING_ACCEPT else self.ui.radio_flag
        button.setChecked(True)

    def _onOverallToggled(self, rating, checked):
        """Applying the overall decision sets every segmentation and measurement row to the same
        value (Approve -> all approved, Flag -> all flagged); rows can then be adjusted individually."""
        if not checked:
            return
        btn_id = {RATING_ACCEPT: 1, RATING_FLAG: 2}[rating]
        for bg in self.seg_button_groups.values():
            bg.button(btn_id).setChecked(True)
        for bg in self.meas_button_groups.values():
            bg.button(btn_id).setChecked(True)

    def _uncheckGroup(self, bg):
        bg.setExclusive(False)
        for btn in bg.buttons():
            btn.setChecked(False)
        bg.setExclusive(True)

    def _resetReviewUI(self):
        if self.overall_button_group:
            self._uncheckGroup(self.overall_button_group)
        for bg in self.seg_button_groups.values():
            self._uncheckGroup(bg)
        for bg in self.meas_button_groups.values():
            self._uncheckGroup(bg)
        self.ui.comment.setPlainText("")

    def _getOverallRating(self):
        if self.ui.radio_accept.isChecked():
            return RATING_ACCEPT
        if self.ui.radio_flag.isChecked():
            return RATING_FLAG
        return RATING_NONE

    @staticmethod
    def _ratings_from_groups(groups):
        mapping = {1: RATING_ACCEPT, 2: RATING_FLAG}
        return {name: mapping.get(bg.checkedId(), RATING_NONE) for name, bg in groups.items()}

    def _getSegRatings(self):
        return self._ratings_from_groups(self.seg_button_groups)

    def _getMeasRatings(self):
        return self._ratings_from_groups(self.meas_button_groups)

    def _saveCurrentReview(self):
        if self.current_index < 0:
            return
        self.case_reviews[self.current_index] = {
            "overall": self._getOverallRating(),
            "segmentation": self._getSegRatings(),
            "measurements": self._getMeasRatings(),
            "comment": self.ui.comment.toPlainText(),
        }

    def _readReviewFromDisk(self, cid):
        if not self.outDir():
            return None
        path = self.casePath(cid, CASE_REVIEW_FILE)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return normalize_review(json.load(f).get("review"))
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not read saved review {path}: {e}")
            return None

    def _restoreReview(self, index):
        review = self.case_reviews.get(index)
        if review is None:
            review = self._readReviewFromDisk(self.caseId(index))
            if review is not None:
                self.case_reviews[index] = review
        self._resetReviewUI()
        if review is None:
            return

        mapping = {RATING_ACCEPT: 1, RATING_FLAG: 2}
        ov = review.get("overall", RATING_NONE)
        self.ui.radio_accept.setChecked(ov == RATING_ACCEPT)
        self.ui.radio_flag.setChecked(ov == RATING_FLAG)

        # Overall toggling auto-fills all rows; per-row values restored below override that.
        for stored, groups in ((review.get("segmentation", {}), self.seg_button_groups),
                               (review.get("measurements", {}), self.meas_button_groups)):
            for name, bg in groups.items():
                self._uncheckGroup(bg)
                btn_id = mapping.get(stored.get(name, RATING_NONE))
                if btn_id:
                    bg.button(btn_id).setChecked(True)
        self.ui.comment.setPlainText(review.get("comment", ""))

    # ------------------------------------------------------------------
    # Saving a review (per-case folder + CSV upsert + status JSON)
    # ------------------------------------------------------------------
    def _numerical_status_to_str(self, status):
        return {0: "No mask found", 1: "Cannot load mask", 2: "Mask loaded, no edits", 3: "Mask edited"}.get(status, "Unknown")

    def _writeCsv(self, cid, review):
        path = os.path.join(self.outDir(), CSV_FILE)
        cols = (["case_id", "file", "comment", "mask_path", "mask_status", "overall"]
                + SEGMENTATION_LABELS + ALL_MEASUREMENT_COLUMNS + ["saved_at"])
        rows = {}
        if os.path.exists(path):
            try:
                with open(path, newline="") as f:
                    for r in csv.DictReader(f):
                        rows[r.get("case_id", "")] = r
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not read existing CSV: {e}")

        sample = self.samples[self.current_index]
        mask_path = self.casePath(cid, CASE_MASK_FILE) if self.status.get(cid, {}).get("mask_edited") \
            else (sample.get("label") or "")
        row = {
            "case_id": cid,
            "file": sample.get("image", ""),
            "comment": review.get("comment", ""),
            "mask_path": mask_path,
            "mask_status": self._numerical_status_to_str(self.mask_status.get(cid, 0)),
            "overall": RATING_TO_STR.get(review.get("overall", RATING_NONE), ""),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        for label in SEGMENTATION_LABELS:
            row[label] = RATING_TO_STR.get(review.get("segmentation", {}).get(label, RATING_NONE), "")
        for meas in ALL_MEASUREMENT_COLUMNS:
            row[meas] = RATING_TO_STR.get(review.get("measurements", {}).get(meas, RATING_NONE), "")
        rows[cid] = row

        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows.values())

    def saveReview(self):
        """Persist the current case's review. Returns True on success."""
        if not self.samples or self.current_index < 0:
            return False
        if not self.outDir():
            slicer.util.errorDisplay("Select an output folder first.")
            return False
        if self._getOverallRating() == RATING_NONE:
            slicer.util.warningDisplay("Please choose Approve or Flag for review before saving.")
            return False

        self._saveCurrentReview()
        cid = self.caseId()
        review = self.case_reviews[self.current_index]
        now = datetime.now().isoformat(timespec="seconds")
        try:
            os.makedirs(self.caseDir(cid), exist_ok=True)
            with open(self.casePath(cid, CASE_REVIEW_FILE), "w") as f:
                json.dump({"case_id": cid, "saved_at": now, "review": review}, f, indent=2)

            entry = self.status.setdefault(cid, {})
            entry["overall"] = review["overall"]
            entry["time"] = now
            self._writeCsv(cid, review)
            self.dumpStatus()
        except Exception as e:
            slicer.util.errorDisplay(f"Could not save review for case {cid}:\n{e}")
            return False

        slicer.util.showStatusMessage(f"Saved review for case {cid}", 3000)
        self.refreshCombo()
        self._updateSummary()
        return True

    def save_and_next_clicked(self):
        if self.n_files == 0 or self.current_index < 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if not self.saveReview():
            return
        if self.current_index + 1 < self.n_files:
            self.loadCase(self.current_index + 1)
        elif all(self.isReviewed(s.get("case_id", "")) for s in self.samples):
            slicer.util.infoDisplay("All cases have been reviewed.", "Finished")
        else:
            self.nextUnreviewed()

    def overwrite_mask_clicked(self):
        """Save the (possibly edited) segmentation into <output>/<case_id>/segmentation.seg.nrrd.
        The original label file is never touched; the edited copy is preferred when the case is re-opened."""
        if not self.samples or self.current_index < 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if not self.outDir():
            slicer.util.warningDisplay("No output folder is set.")
            return
        seg = self.segmentation_node or slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')
        if not seg:
            slicer.util.warningDisplay("No segmentation node found to save.")
            return

        cid = self.caseId()
        os.makedirs(self.caseDir(cid), exist_ok=True)
        path = self.casePath(cid, CASE_MASK_FILE)
        if not slicer.util.saveNode(seg, path):
            slicer.util.errorDisplay(f"Could not save segmentation to:\n{path}")
            return
        self.mask_status[cid] = 3
        entry = self.status.setdefault(cid, {})
        entry["mask_edited"] = True
        entry["mask_saved_at"] = datetime.now().isoformat(timespec="seconds")
        self.dumpStatus()
        slicer.util.infoDisplay(f"Segmentation saved successfully as:\n{path}")

    # ------------------------------------------------------------------
    # View alignment
    # ------------------------------------------------------------------
    def _createAlignmentWidget_(self):
        alignmentCollapsibleButton = ctk.ctkCollapsibleButton()
        alignmentCollapsibleButton.text = "View Alignment"
        self.layout.addWidget(alignmentCollapsibleButton)
        alignmentFormLayout = qt.QFormLayout(alignmentCollapsibleButton)

        self.alignmentTargetComboBox = qt.QComboBox()
        self.alignmentTargetComboBox.addItem("Default orientation")
        self.alignmentTargetComboBox.addItem("contours.annulus")
        self.alignmentTargetComboBox.addItem("contours.sov")
        self.alignmentTargetComboBox.addItem("contours.stj")
        self.alignmentTargetComboBox.setCurrentIndex(1)
        alignmentFormLayout.addRow("Alignment target:", self.alignmentTargetComboBox)

        self.applyAlignmentButton = qt.QPushButton("Apply Alignment / Reset Views")
        self.applyAlignmentButton.connect('clicked(bool)', self.onApplyAlignmentClicked)
        alignmentFormLayout.addRow(self.applyAlignmentButton)

    def onApplyAlignmentClicked(self):
        if not hasattr(self, "alignmentTargetComboBox") or self.alignmentTargetComboBox is None:
            return
        target = str(self.alignmentTargetComboBox.currentText).strip().lower()
        if target in ["default orientation", "default", "reset", "reset views", "default views"]:
            self.reset_views_to_default()
            return
        contour_node = self.contour_nodes_by_label.get(target, None)
        if contour_node is None:
            slicer.util.warningDisplay(
                f"No loaded markup found for '{target}'.\n\n"
                "Load a case that contains this contour, or choose another target."
            )
            return
        self.align_views_to_contour(contour_node, target)

    # ------------------------------------------------------------------
    # Centerline slicing (slider-driven CPR-style axial alignment)
    # ------------------------------------------------------------------
    def _createCenterlineSlicingWidget_(self):
        centerlineCollapsibleButton = ctk.ctkCollapsibleButton()
        centerlineCollapsibleButton.text = "Centerline Slicing"
        self.layout.addWidget(centerlineCollapsibleButton)
        centerlineLayout = qt.QFormLayout(centerlineCollapsibleButton)

        self.centerlineTargetComboBox = qt.QComboBox()
        self.centerlineTargetComboBox.addItem("No centerline loaded")
        self.centerlineTargetComboBox.setEnabled(False)
        centerlineLayout.addRow("Centerline:", self.centerlineTargetComboBox)

        self.centerlineEnableCheckBox = qt.QCheckBox("Lock axial (Red) view to centerline")
        self.centerlineEnableCheckBox.setChecked(False)
        self.centerlineEnableCheckBox.setEnabled(False)
        centerlineLayout.addRow(self.centerlineEnableCheckBox)

        sliderLayout = qt.QHBoxLayout()
        self.centerlineSlider = qt.QSlider(qt.Qt.Horizontal)
        self.centerlineSlider.setMinimum(0)
        self.centerlineSlider.setMaximum(0)
        self.centerlineSlider.setEnabled(False)
        self.centerlinePositionLabel = qt.QLabel("0 / 0  (0.0 mm)")
        self.centerlinePositionLabel.setMinimumWidth(140)
        sliderLayout.addWidget(self.centerlineSlider)
        sliderLayout.addWidget(self.centerlinePositionLabel)
        centerlineLayout.addRow("Position:", sliderLayout)

        self.centerlineSliceSizeSpinBox = qt.QDoubleSpinBox()
        self.centerlineSliceSizeSpinBox.setRange(10.0, 300.0)
        self.centerlineSliceSizeSpinBox.setSingleStep(5.0)
        self.centerlineSliceSizeSpinBox.setValue(80.0)
        self.centerlineSliceSizeSpinBox.setSuffix(" mm")
        centerlineLayout.addRow("Cross-section size:", self.centerlineSliceSizeSpinBox)

        self.centerlineTargetComboBox.currentIndexChanged.connect(self.onCenterlineTargetChanged)
        self.centerlineEnableCheckBox.toggled.connect(self.onCenterlineEnableToggled)
        self.centerlineSlider.valueChanged.connect(self.onCenterlineSliderChanged)
        self.centerlineSliceSizeSpinBox.valueChanged.connect(self.onCenterlineSliceSizeChanged)

    def _centerline_tangent(self, points, index):
        n = points.shape[0]
        if n < 2:
            return np.array([0.0, 0.0, 1.0])
        i0 = max(0, index - 1)
        i1 = min(n - 1, index + 1)
        if i0 == i1:
            return np.array([0.0, 0.0, 1.0])
        tangent = points[i1] - points[i0]
        norm = np.linalg.norm(tangent)
        if norm < 1e-6:
            return np.array([0.0, 0.0, 1.0])
        return tangent / norm

    def _compute_centerline_arrays(self, label, node):
        points = self._get_markup_points_world(node) if node is not None else None
        if points is None or points.shape[0] < 2:
            self.centerline_points_world[label] = None
            self.centerline_arclength[label] = None
            return
        diffs = np.diff(points, axis=0)
        seglen = np.linalg.norm(diffs, axis=1)
        cumulative = np.concatenate([[0.0], np.cumsum(seglen)])
        self.centerline_points_world[label] = points
        self.centerline_arclength[label] = cumulative

    def _refreshCenterlineTargets(self):
        if not hasattr(self, "centerlineTargetComboBox"):
            return

        self.centerlineTargetComboBox.blockSignals(True)
        self.centerlineTargetComboBox.clear()

        labels = sorted(self.centerline_nodes_by_label.keys())
        if not labels:
            self.centerlineTargetComboBox.addItem("No centerline loaded")
            self.centerlineTargetComboBox.setEnabled(False)
            self.centerlineEnableCheckBox.setEnabled(False)
            self.centerlineEnableCheckBox.setChecked(False)
            self.centerlineSlider.setEnabled(False)
            self.centerlineSlider.setMaximum(0)
            self.centerlinePositionLabel.setText("0 / 0  (0.0 mm)")
            self.centerlineTargetComboBox.blockSignals(False)
            return

        preferred = "centerline.points"
        for label in labels:
            self._compute_centerline_arrays(label, self.centerline_nodes_by_label[label])
            self.centerlineTargetComboBox.addItem(label)

        default_index = labels.index(preferred) if preferred in labels else 0
        self.centerlineTargetComboBox.setCurrentIndex(default_index)
        self.centerlineTargetComboBox.setEnabled(True)
        self.centerlineEnableCheckBox.setEnabled(True)
        self.centerlineTargetComboBox.blockSignals(False)

        self._updateCenterlineSliderRange()

    def _updateCenterlineSliderRange(self):
        label = self.centerlineTargetComboBox.currentText
        points = self.centerline_points_world.get(label)
        if points is None or points.shape[0] < 2:
            self.centerlineSlider.setEnabled(False)
            self.centerlineSlider.setMaximum(0)
            self.centerlinePositionLabel.setText("0 / 0  (0.0 mm)")
            return
        self.centerlineSlider.blockSignals(True)
        self.centerlineSlider.setMinimum(0)
        self.centerlineSlider.setMaximum(points.shape[0] - 1)
        self.centerlineSlider.setValue(0)
        self.centerlineSlider.blockSignals(False)
        self.centerlineSlider.setEnabled(True)
        self._updateCenterlinePositionLabel(0)
        if self.centerlineEnableCheckBox.isChecked():
            self._applyCenterlineSlicePosition(0)

    def _updateCenterlinePositionLabel(self, index):
        label = self.centerlineTargetComboBox.currentText
        points = self.centerline_points_world.get(label)
        cumulative = self.centerline_arclength.get(label)
        if points is None:
            self.centerlinePositionLabel.setText("0 / 0  (0.0 mm)")
            return
        n = points.shape[0]
        dist = cumulative[index] if cumulative is not None else 0.0
        self.centerlinePositionLabel.setText(f"{index + 1} / {n}  ({dist:.1f} mm)")

    def onCenterlineTargetChanged(self, _index=None):
        self._updateCenterlineSliderRange()

    def onCenterlineEnableToggled(self, checked):
        if checked:
            self._applyCenterlineSlicePosition(self.centerlineSlider.value)

    def onCenterlineSliceSizeChanged(self, _value=None):
        if self.centerlineEnableCheckBox.isChecked():
            self._applyCenterlineSlicePosition(self.centerlineSlider.value)

    def onCenterlineSliderChanged(self, value):
        self._updateCenterlinePositionLabel(value)
        if not self.centerlineEnableCheckBox.isChecked():
            return
        self._applyCenterlineSlicePosition(value)

    def _applyCenterlineSlicePosition(self, index):
        label = self.centerlineTargetComboBox.currentText
        points = self.centerline_points_world.get(label)
        if points is None or points.shape[0] == 0:
            return
        index = int(max(0, min(index, points.shape[0] - 1)))
        point = points[index]
        tangent = self._centerline_tangent(points, index)
        x_axis, y_axis, z_axis = self._orthogonal_axes_from_normal(tangent)

        layoutManager = slicer.app.layoutManager()
        view_names = layoutManager.sliceViewNames()
        if len(view_names) < 1:
            return
        if len(view_names) < 3:
            try:
                four_up = getattr(slicer.vtkMRMLLayoutNode, "SlicerLayoutFourUp", None)
                if four_up is not None:
                    layoutManager.setLayout(four_up)
                    slicer.app.processEvents()
                    view_names = layoutManager.sliceViewNames()
            except Exception as e:
                print(f"[Centerline] Could not switch layout to Four-Up: {e}")
        if self.volume_node:
            try:
                slicer.util.setSliceViewerLayers(background=self.volume_node)
            except Exception as e:
                print(f"[Centerline] Could not re-set background volume: {e}")

        fov_size = float(self.centerlineSliceSizeSpinBox.value) if hasattr(self, "centerlineSliceSizeSpinBox") else 80.0
        shared_fov = (fov_size, fov_size)

        red_view = "Red" if "Red" in view_names else (view_names[0] if len(view_names) > 0 else None)
        yellow_view = "Yellow" if "Yellow" in view_names else (view_names[1] if len(view_names) > 1 else None)
        green_view = "Green" if "Green" in view_names else (view_names[2] if len(view_names) > 2 else None)

        if red_view:
            self._set_slice_view_plane(red_view, x_axis, y_axis, z_axis, point, shared_fov)
        else:
            print("[Centerline] No Red-equivalent slice view found.")
        if yellow_view:
            self._set_slice_view_plane(yellow_view, x_axis, z_axis, -y_axis, point, shared_fov)
        else:
            print("[Centerline] No Yellow-equivalent slice view found.")
        if green_view:
            self._set_slice_view_plane(green_view, y_axis, z_axis, x_axis, point, shared_fov)
        else:
            print("[Centerline] No Green-equivalent slice view found.")

        try:
            layoutManager.forceRender()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Segmentation loading
    # ------------------------------------------------------------------
    def _load_segmentation_flexible(self, path):
        try:
            segmentation_node = slicer.util.loadSegmentation(path)
            if segmentation_node:
                return segmentation_node
        except Exception as e:
            print(f"[TavrWorkbench] loadSegmentation failed for {path}: {e}")
        try:
            labelmap_node = slicer.util.loadLabelVolume(path)
            if not labelmap_node:
                return None
            segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmap_node, segmentation_node)
            slicer.mrmlScene.RemoveNode(labelmap_node)
            return segmentation_node
        except Exception as e:
            print(f"[TavrWorkbench] Could not load segmentation from {path}: {e}")
            logging.getLogger('TavrWorkbench').info(f'Could not load segmentation from {path}: {e}')
            return None

    # ------------------------------------------------------------------
    # Markups widget helpers
    # ------------------------------------------------------------------
    def _enableWidgetRecursively(self, widget):
        if not widget:
            return
        try:
            widget.setEnabled(True)
        except Exception:
            pass
        try:
            for child in widget.findChildren(qt.QWidget):
                try:
                    child.setEnabled(True)
                except Exception:
                    pass
        except Exception:
            pass

    def _deferredEnableMarkupsOptions(self):
        try:
            self._enableMarkupsWidgetOptions(False)
        except Exception:
            pass

    def _enableMarkupsWidgetOptions(self, reschedule=True):
        if not hasattr(self, "markupsWidget") or self.markupsWidget is None:
            return
        try:
            self.markupsWidget.setEnabled(True)
            self._enableWidgetRecursively(self.markupsWidget)
            try:
                collapsibles = self.markupsWidget.findChildren(ctk.ctkCollapsibleButton)
                for button in collapsibles:
                    try:
                        button.setEnabled(True)
                        if hasattr(button, "collapsed"):
                            button.collapsed = False
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                tabWidgets = self.markupsWidget.findChildren(qt.QTabWidget)
                for tabWidget in tabWidgets:
                    try:
                        count = tabWidget.count
                        if callable(count):
                            count = count()
                        for i in range(int(count)):
                            tabWidget.setTabEnabled(i, True)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                for child in self.markupsWidget.findChildren(qt.QWidget):
                    try:
                        child.setEnabled(True)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not enable Markups options: {e}")
        if reschedule:
            try:
                qt.QTimer.singleShot(0, self._deferredEnableMarkupsOptions)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def _get_markup_points_world(self, markup_node):
        points = []
        for methodName in ["GetCurvePointsWorld", "GetCurveWorld"]:
            if not hasattr(markup_node, methodName):
                continue
            try:
                obj = getattr(markup_node, methodName)()
                if obj is None:
                    continue
                vtk_points = None
                if hasattr(obj, "GetNumberOfPoints") and hasattr(obj, "GetPoint"):
                    vtk_points = obj
                elif hasattr(obj, "GetPoints"):
                    vtk_points = obj.GetPoints()
                if vtk_points is not None:
                    n = vtk_points.GetNumberOfPoints()
                    for i in range(n):
                        points.append(list(vtk_points.GetPoint(i)))
                    if len(points) >= 3:
                        return np.array(points, dtype=float)
            except Exception as e:
                print(f"[Alignment] Dense point extraction failed using {methodName}: {e}")
        if hasattr(markup_node, "GetNumberOfControlPoints"):
            n = markup_node.GetNumberOfControlPoints()
            for i in range(n):
                p = [0.0, 0.0, 0.0]
                try:
                    if hasattr(markup_node, "GetNthControlPointPositionWorld"):
                        markup_node.GetNthControlPointPositionWorld(i, p)
                    else:
                        markup_node.GetNthControlPointPosition(i, p)
                    points.append(p)
                except Exception as e:
                    print(f"[Alignment] Failed to get control point {i}: {e}")
        return np.array(points, dtype=float)

    def _orthogonal_axes_from_normal(self, normal):
        n = np.array(normal, dtype=float)
        n_norm = np.linalg.norm(n)
        if n_norm < 1e-9:
            return np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])
        n /= n_norm
        reference_axes = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ]
        x_axis = None
        for ref in reference_axes:
            candidate = ref - np.dot(ref, n) * n
            candidate_norm = np.linalg.norm(candidate)
            if candidate_norm > 1e-3:
                x_axis = candidate / candidate_norm
                break
        if x_axis is None:
            x_axis = np.array([1.0, 0.0, 0.0])
        y_axis = np.cross(n, x_axis)
        y_norm = np.linalg.norm(y_axis)
        if y_norm < 1e-9:
            y_axis = np.array([0.0, 1.0, 0.0])
        else:
            y_axis /= y_norm
        x_axis = np.cross(y_axis, n)
        x_norm = np.linalg.norm(x_axis)
        if x_norm < 1e-9:
            x_axis = np.array([1.0, 0.0, 0.0])
        else:
            x_axis /= x_norm
        return x_axis, y_axis, n

    def _required_square_fov_for_plane(self, points, origin, x_axis, y_axis, margin=1.8, min_size=60.0):
        if points is None or len(points) == 0:
            return min_size, min_size
        v = points - origin
        xs = np.dot(v, x_axis)
        ys = np.dot(v, y_axis)
        range_x = float(np.max(xs) - np.min(xs)) if xs.size else 0.0
        range_y = float(np.max(ys) - np.min(ys)) if ys.size else 0.0
        extent = max(range_x, range_y, float(min_size))
        fov = extent * float(margin)
        return fov, fov

    def _set_slice_view_plane(self, view_name, x_axis, y_axis, z_axis, origin, required_fov=None):
        layoutManager = slicer.app.layoutManager()
        sliceWidget = layoutManager.sliceWidget(view_name)
        if not sliceWidget:
            print(f"[Alignment] Slice view {view_name} not found.")
            return False
        sliceNode = sliceWidget.mrmlSliceNode()
        if not sliceNode:
            print(f"[Alignment] Slice node for {view_name} not found.")
            return False
        sliceLogic = None
        try:
            sliceLogic = slicer.app.applicationLogic().GetSliceLogic(sliceNode)
        except Exception:
            sliceLogic = None
        if sliceLogic is None:
            try:
                sliceLogic = sliceWidget.sliceLogic()
            except Exception:
                sliceLogic = None
        x = np.array(x_axis, dtype=float)
        y = np.array(y_axis, dtype=float)
        x_norm = np.linalg.norm(x)
        if x_norm < 1e-9:
            print(f"[Alignment] Invalid X axis for {view_name}.")
            return False
        x /= x_norm
        y = y - np.dot(y, x) * x
        y_norm = np.linalg.norm(y)
        if y_norm < 1e-9:
            fallback = np.array([0.0, 0.0, 1.0])
            y = np.cross(fallback, x)
            y_norm = np.linalg.norm(y)
            if y_norm < 1e-9:
                fallback = np.array([1.0, 0.0, 0.0])
                y = np.cross(fallback, x)
                y_norm = np.linalg.norm(y)
        y /= y_norm
        z = np.cross(x, y)
        z_norm = np.linalg.norm(z)
        if z_norm < 1e-9:
            print(f"[Alignment] Could not construct a valid Z axis for {view_name}.")
            return False
        z /= z_norm
        transform = vtk.vtkMatrix4x4()
        transform.Identity()
        for i in range(3):
            transform.SetElement(i, 0, float(x[i]))
            transform.SetElement(i, 1, float(y[i]))
            transform.SetElement(i, 2, float(z[i]))
            transform.SetElement(i, 3, float(origin[i]))
        wasModified = sliceNode.StartModify()
        try:
            orientation_set = False
            for methodName in ["SetOrientationToReformat", "SetOrientationToUser"]:
                if hasattr(sliceNode, methodName):
                    try:
                        getattr(sliceNode, methodName)()
                        orientation_set = True
                        break
                    except Exception as e:
                        print(f"[Alignment] {view_name}: {methodName} failed: {e}")
            if not orientation_set:
                try:
                    sliceNode.SetOrientation("Reformat")
                except Exception as e:
                    print(f"[Alignment] {view_name}: SetOrientation('Reformat') failed: {e}")
            if hasattr(sliceNode, "SetSliceToRAS"):
                try:
                    sliceNode.SetSliceToRAS(transform)
                except Exception as e:
                    print(f"[Alignment] {view_name}: SetSliceToRAS failed: {e}")
            try:
                sliceNode.GetSliceToRAS().DeepCopy(transform)
            except Exception as e:
                print(f"[Alignment] {view_name}: DeepCopy SliceToRAS failed: {e}")
            try:
                sliceNode.UpdateMatrices()
            except Exception as e:
                print(f"[Alignment] {view_name}: UpdateMatrices failed: {e}")
            if hasattr(sliceNode, "JumpSlice"):
                try:
                    sliceNode.JumpSlice(float(origin[0]), float(origin[1]), float(origin[2]))
                except Exception as e:
                    print(f"[Alignment] {view_name}: JumpSlice failed: {e}")
            sliceNode.Modified()
        finally:
            sliceNode.EndModify(wasModified)
        if sliceLogic:
            try:
                sliceLogic.FitSliceToAll()
            except Exception as e:
                print(f"[Alignment] {view_name}: FitSliceToAll failed: {e}")
        if hasattr(sliceNode, "JumpSlice"):
            try:
                sliceNode.JumpSlice(float(origin[0]), float(origin[1]), float(origin[2]))
            except Exception:
                pass
        if required_fov:
            if hasattr(sliceNode, "SetFieldOfView"):
                wasModified = sliceNode.StartModify()
                try:
                    sliceNode.SetFieldOfView(float(required_fov[0]), float(required_fov[1]))
                except Exception as e:
                    print(f"[Alignment] {view_name}: SetFieldOfView failed: {e}")
                finally:
                    sliceNode.EndModify(wasModified)
            elif sliceLogic and hasattr(sliceLogic, "FitSliceToContent"):
                try:
                    sliceLogic.FitSliceToContent()
                except Exception as e:
                    print(f"[Alignment] {view_name}: FitSliceToContent failed: {e}")
            if hasattr(sliceNode, "JumpSlice"):
                try:
                    sliceNode.JumpSlice(float(origin[0]), float(origin[1]), float(origin[2]))
                except Exception:
                    pass
        try:
            sliceWidget.forceRender()
        except Exception:
            pass
        return True

    def align_views_to_contour(self, curve_node, contour_label="contour"):
        if not curve_node:
            print("[Alignment] No contour node provided.")
            return
        node_name = curve_node.GetName() if hasattr(curve_node, "GetName") else "unknown"
        print(f"[Alignment] Aligning views using contour: {contour_label} ({node_name})")
        points = self._get_markup_points_world(curve_node)
        if points.size == 0 or points.shape[0] < 3:
            slicer.util.warningDisplay(f"Not enough points were found in '{contour_label}' to define a plane.")
            return
        if not np.all(np.isfinite(points)):
            slicer.util.warningDisplay(f"Contour points for '{contour_label}' contain invalid coordinates.")
            return
        centroid = np.mean(points, axis=0)
        centered = points - centroid
        if np.linalg.norm(centered) < 1e-6:
            slicer.util.warningDisplay(f"Contour points for '{contour_label}' are degenerate.")
            return
        try:
            u, s, vh = np.linalg.svd(centered)
        except Exception as e:
            slicer.util.warningDisplay(f"Plane fitting failed for '{contour_label}': {e}")
            return
        normal = vh[2].astype(float)
        if np.linalg.norm(normal) < 1e-9:
            slicer.util.warningDisplay(f"Could not compute a plane normal for '{contour_label}'.")
            return
        if normal[2] < 0:
            normal = -normal
        x_axis, y_axis, z_axis = self._orthogonal_axes_from_normal(normal)
        layoutManager = slicer.app.layoutManager()
        if len(layoutManager.sliceViewNames()) < 3:
            try:
                four_up = getattr(slicer.vtkMRMLLayoutNode, "SlicerLayoutFourUp", None)
                if four_up is not None:
                    layoutManager.setLayout(four_up)
                    slicer.app.processEvents()
            except Exception as e:
                print(f"[Alignment] Could not switch layout to Four-Up: {e}")
        if self.volume_node:
            try:
                slicer.util.setSliceViewerLayers(background=self.volume_node)
            except Exception as e:
                print(f"[Alignment] Could not re-set background volume: {e}")
        shared_fov = self._required_square_fov_for_plane(
            points, centroid, x_axis, y_axis, margin=1.8, min_size=60.0
        )
        view_names = layoutManager.sliceViewNames()
        red_view = "Red" if "Red" in view_names else (view_names[0] if len(view_names) > 0 else None)
        yellow_view = "Yellow" if "Yellow" in view_names else (view_names[1] if len(view_names) > 1 else None)
        green_view = "Green" if "Green" in view_names else (view_names[2] if len(view_names) > 2 else None)
        if red_view:
            self._set_slice_view_plane(red_view, x_axis, y_axis, z_axis, centroid, shared_fov)
        if yellow_view:
            self._set_slice_view_plane(yellow_view, x_axis, z_axis, -y_axis, centroid, shared_fov)
        if green_view:
            self._set_slice_view_plane(green_view, y_axis, z_axis, x_axis, centroid, shared_fov)
        try:
            layoutManager.forceRender()
        except Exception:
            pass

    def align_views_to_annulus(self, curve_node):
        self.align_views_to_contour(curve_node, "contours.annulus")

    def _set_standard_slice_orientation(self, sliceNode, orientation_name):
        if not sliceNode:
            return False
        method_map = {
            "Axial": "SetOrientationToAxial",
            "Sagittal": "SetOrientationToSagittal",
            "Coronal": "SetOrientationToCoronal",
        }
        method_name = method_map.get(orientation_name)
        if method_name and hasattr(sliceNode, method_name):
            try:
                getattr(sliceNode, method_name)()
                return True
            except Exception as e:
                print(f"[Alignment] {method_name} failed: {e}")
        try:
            sliceNode.SetOrientation(orientation_name)
            return True
        except Exception as e:
            print(f"[Alignment] SetOrientation('{orientation_name}') failed: {e}")
        return False

    def _reset_one_slice_view_to_orientation(self, view_name, orientation_name):
        if not view_name:
            return
        layoutManager = slicer.app.layoutManager()
        sliceWidget = layoutManager.sliceWidget(view_name)
        if not sliceWidget:
            return
        sliceNode = sliceWidget.mrmlSliceNode()
        if not sliceNode:
            return
        wasModified = sliceNode.StartModify()
        try:
            self._set_standard_slice_orientation(sliceNode, orientation_name)
            try:
                sliceNode.UpdateMatrices()
            except Exception:
                pass
        finally:
            sliceNode.EndModify(wasModified)
        sliceLogic = None
        try:
            sliceLogic = slicer.app.applicationLogic().GetSliceLogic(sliceNode)
        except Exception:
            sliceLogic = None
        if sliceLogic is None:
            try:
                sliceLogic = sliceWidget.sliceLogic()
            except Exception:
                sliceLogic = None
        if sliceLogic:
            try:
                sliceLogic.FitSliceToAll()
            except Exception:
                pass
        try:
            sliceWidget.forceRender()
        except Exception:
            pass

    def reset_views_to_default(self):
        layoutManager = slicer.app.layoutManager()
        if len(layoutManager.sliceViewNames()) < 3:
            try:
                four_up = getattr(slicer.vtkMRMLLayoutNode, "SlicerLayoutFourUp", None)
                if four_up is not None:
                    layoutManager.setLayout(four_up)
                    slicer.app.processEvents()
            except Exception as e:
                print(f"[Alignment] Could not switch layout to Four-Up: {e}")
        if self.volume_node:
            try:
                slicer.util.setSliceViewerLayers(background=self.volume_node)
            except Exception as e:
                print(f"[Alignment] Could not set background volume during reset: {e}")
        view_names = layoutManager.sliceViewNames()
        red_view = "Red" if "Red" in view_names else (view_names[0] if len(view_names) > 0 else None)
        yellow_view = "Yellow" if "Yellow" in view_names else (view_names[1] if len(view_names) > 1 else None)
        green_view = "Green" if "Green" in view_names else (view_names[2] if len(view_names) > 2 else None)
        self._reset_one_slice_view_to_orientation(red_view, "Axial")
        self._reset_one_slice_view_to_orientation(yellow_view, "Sagittal")
        self._reset_one_slice_view_to_orientation(green_view, "Coronal")
        try:
            layoutManager.forceRender()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Case loading
    # ------------------------------------------------------------------
    def _clearCaseNodes(self):
        """Remove every MRML node belonging to the currently loaded case."""
        if self.volume_node:
            self.store_current_window_level_settings()
        if self.segmentation_node:
            self.store_segment_visiblity_states()

        nodes_to_remove = set()
        candidates = [self.volume_node, self.segmentation_node, self.pointListNode]
        if hasattr(self, "segmentEditorWidget") and self.segmentEditorWidget is not None:
            try:
                candidates.append(self.segmentEditorWidget.segmentationNode())
            except Exception:
                pass
        candidates += self.loaded_markup_nodes + self.loaded_model_nodes
        for node in candidates:
            if node:
                nodes_to_remove.add(node)
        for node in nodes_to_remove:
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: failed removing node: {e}")
        self.loaded_markup_nodes = []
        self.loaded_model_nodes = []
        self.volume_node = None
        self.segmentation_node = None
        self.pointListNode = None
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self.centerline_points_world = {}
        self.centerline_arclength = {}

    def _loadCaseData(self):
        self._clearCaseNodes()
        sample = self.samples[self.current_index]
        cid = self.caseId()
        logger = logging.getLogger('TavrWorkbench')

        image_path = sample.get("image", "")
        print(f"[TavrWorkbench] Loading case {cid} ({self.current_index + 1}/{self.n_files}): {image_path}")

        # Prefer an edited mask saved in the output folder, otherwise the original label
        label_path = sample.get("label", "") or ""
        edited_mask = self.casePath(cid, CASE_MASK_FILE) if self.outDir() else ""
        from_saved_mask = bool(edited_mask and os.path.exists(edited_mask))
        if from_saved_mask:
            label_path = edited_mask
        if not (isinstance(label_path, str) and os.path.exists(label_path)
                and (from_saved_mask or self._is_valid_extension(label_path))):
            label_path = ""

        case_markups, case_models = self._collect_case_assets(sample)

        slicer.app.layoutManager().setRenderPaused(True)
        try:
            try:
                self.volume_node = slicer.util.loadVolume(image_path)
            except Exception as e:
                print(f"[TavrWorkbench] ERROR loading volume {image_path}: {e}")
                slicer.util.errorDisplay(f"Could not load volume for case {cid}:\n{image_path}\n\n{e}")
                self.volume_node = None
            if self.volume_node is None:
                self._refreshCenterlineTargets()
                return
            slicer.util.setSliceViewerLayers(background=self.volume_node)
            self.restore_window_level_settings()

            if label_path:
                self.segmentation_node = self._load_segmentation_flexible(label_path)
                if self.segmentation_node:
                    self.mask_status[cid] = 3 if from_saved_mask else 2
                    self.restore_segment_visiblity_states()
                    try:
                        self.set_segmentation_and_mask_for_segmentation_editor()
                    except Exception as e:
                        print(f"[TavrWorkbench] WARNING: could not initialize segment editor for {label_path}: {e}")
                else:
                    self.mask_status[cid] = 1
                    print(f"[TavrWorkbench] WARNING: segmentation could not be loaded for case {cid}: {label_path}")
            else:
                self.mask_status[cid] = 1 if sample.get("label") else 0
                logger.info(f'Case {cid}: no usable segmentation label found')

            for label, path in case_markups.items():
                try:
                    markupNode = slicer.util.loadMarkups(path)
                    if markupNode:
                        markupNode.SetName(label)
                        if not markupNode.GetDisplayNode():
                            markupNode.CreateDefaultDisplayNodes()
                        displayNode = markupNode.GetDisplayNode()
                        displayNode.SetVisibility(True)
                        if hasattr(displayNode, "SetSliceIntersectionVisibility"):
                            try:
                                displayNode.SetSliceIntersectionVisibility(True)
                            except Exception:
                                pass
                        self.loaded_markup_nodes.append(markupNode)
                        lower_label = label.lower()
                        if lower_label in ["contours.annulus", "contours.sov", "contours.stj"]:
                            self.contour_nodes_by_label[lower_label] = markupNode
                        if lower_label.startswith("centerline."):
                            self.centerline_nodes_by_label[lower_label] = markupNode
                    else:
                        print(f"[TavrWorkbench] WARNING: loadMarkups returned None for {label}: {path}")
                except Exception as e:
                    print(f"[TavrWorkbench] WARNING: could not load markup {label} from {path}: {e}")

            # Centerline models (surface.vtp / centerline.vtp): loaded as models, not reviewed
            for label, path in case_models.items():
                try:
                    modelNode = slicer.util.loadModel(path)
                    if modelNode:
                        modelNode.SetName(label)
                        if not modelNode.GetDisplayNode():
                            modelNode.CreateDefaultDisplayNodes()
                        displayNode = modelNode.GetDisplayNode()
                        if displayNode:
                            displayNode.SetVisibility(True)
                            lower_label = label.lower()
                            if lower_label.endswith("surface"):
                                displayNode.SetColor(0.9, 0.85, 0.2)
                                displayNode.SetOpacity(0.35)
                            elif lower_label.endswith("curve"):
                                displayNode.SetColor(1.0, 0.1, 0.1)
                                if hasattr(displayNode, "SetLineWidth"):
                                    displayNode.SetLineWidth(3)
                            if hasattr(displayNode, "SetSliceIntersectionVisibility"):
                                try:
                                    displayNode.SetSliceIntersectionVisibility(True)
                                except Exception:
                                    pass
                        self.loaded_model_nodes.append(modelNode)
                    else:
                        print(f"[TavrWorkbench] WARNING: loadModel returned None for {label}: {path}")
                except Exception as e:
                    print(f"[TavrWorkbench] WARNING: could not load model {label} from {path}: {e}")
        finally:
            slicer.app.layoutManager().setRenderPaused(False)
            slicer.app.processEvents()

        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            try:
                layoutManager.sliceWidget(sliceViewName).sliceLogic().FitSliceToAll()
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: FitSliceToAll failed for {sliceViewName}: {e}")

        active_markup = None
        selected_alignment = ""
        if hasattr(self, "alignmentTargetComboBox") and self.alignmentTargetComboBox is not None:
            selected_alignment = str(self.alignmentTargetComboBox.currentText).strip().lower()
        if selected_alignment in self.contour_nodes_by_label:
            active_markup = self.contour_nodes_by_label[selected_alignment]
        elif "contours.annulus" in self.contour_nodes_by_label:
            active_markup = self.contour_nodes_by_label["contours.annulus"]
        elif "contours.sov" in self.contour_nodes_by_label:
            active_markup = self.contour_nodes_by_label["contours.sov"]
        elif "contours.stj" in self.contour_nodes_by_label:
            active_markup = self.contour_nodes_by_label["contours.stj"]
        elif self.loaded_markup_nodes:
            active_markup = self.loaded_markup_nodes[0]
        if active_markup is not None:
            try:
                slicer.modules.markups.logic().SetActiveListID(active_markup)
            except Exception:
                try:
                    slicer.modules.markups.logic().SetActiveListID(active_markup.GetID())
                except Exception as e:
                    print(f"[TavrWorkbench] WARNING: could not set active markup node: {e}")
        self._enableMarkupsWidgetOptions()
        self._refreshCenterlineTargets()

    # ------------------------------------------------------------------
    # Segment editor / markups widgets
    # ------------------------------------------------------------------
    def _createSegmentEditorWidget_(self):
        import qSlicerSegmentationsModuleWidgetsPythonQt
        segmentEditorCollapsibleButton = ctk.ctkCollapsibleButton()
        segmentEditorCollapsibleButton.text = "Segmentation Editor"
        self.layout.addWidget(segmentEditorCollapsibleButton)
        segmentEditorLayout = qt.QVBoxLayout(segmentEditorCollapsibleButton)
        self.segmentEditorWidget = qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget()
        self.segmentEditorWidget.setMaximumNumberOfUndoStates(10)
        self.selectParameterNode()
        self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.segmentEditorWidget.unorderedEffectsVisible = False
        self.segmentEditorWidget.setEffectNameOrder([
            'No editing', 'Threshold',
            'Paint', 'Draw',
            'Erase', 'Level tracing',
            'Grow from seeds', 'Fill between slices',
            'Margin', 'Hollow',
            'Smoothing', 'Scissors',
            'Islands', 'Logical operators',
            'Mask volume'])
        segmentEditorLayout.addWidget(self.segmentEditorWidget)

    def _createMarkupWidget_(self):
        markupsCollapsibleButton = ctk.ctkCollapsibleButton()
        markupsCollapsibleButton.text = "Markups"
        self.layout.addWidget(markupsCollapsibleButton)
        markupsLayout = qt.QVBoxLayout(markupsCollapsibleButton)
        markupsModule = slicer.util.getModule('Markups')
        self.markupsWidget = markupsModule.createNewWidgetRepresentation()
        if hasattr(self.markupsWidget, "setMRMLScene"):
            try:
                self.markupsWidget.setMRMLScene(slicer.mrmlScene)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not set MRML scene on Markups widget: {e}")
        if hasattr(self.markupsWidget, "enter"):
            try:
                self.markupsWidget.enter()
            except Exception:
                pass
        markupsLayout.addWidget(self.markupsWidget)
        self._enableMarkupsWidgetOptions()

    def enter(self):
        self.selectParameterNode()
        self.segmentEditorWidget.updateWidgetFromMRML()
        if not self.segmentEditorWidget.segmentationNodeID():
            self.segmentation_node = slicer.mrmlScene.GetFirstNode(None, "vtkMRMLSegmentationNode")
            if not self.segmentation_node:
                self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
            if not self.segmentEditorWidget.sourceVolumeNodeID():
                self.sourceVolumeNodeID = self.getDefaultSourceVolumeNodeID()
                self.segmentEditorWidget.setSourceVolumeNodeID(self.sourceVolumeNodeID)
        self.initializeParameterNode()
        self._enableMarkupsWidgetOptions()

    def getDefaultSourceVolumeNodeID(self):
        layoutManager = slicer.app.layoutManager()
        firstForegroundVolumeID = None
        for sliceViewName in layoutManager.sliceViewNames():
            sliceWidget = layoutManager.sliceWidget(sliceViewName)
            if not sliceWidget:
                continue
            compositeNode = sliceWidget.mrmlSliceCompositeNode()
            if compositeNode.GetBackgroundVolumeID():
                return compositeNode.GetBackgroundVolumeID()
            if compositeNode.GetForegroundVolumeID() and not firstForegroundVolumeID:
                firstForegroundVolumeID = compositeNode.GetForegroundVolumeID()
        return firstForegroundVolumeID

    def selectParameterNode(self):
        segmentEditorSingletonTag = "SegmentEditor"
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        self.parameterSetNode = segmentEditorNode
        self.segmentEditorWidget.setMRMLSegmentEditorNode(self.parameterSetNode)

    # ------------------------------------------------------------------
    # Window/level + segment visibility persistence across cases
    # ------------------------------------------------------------------
    def store_current_window_level_settings(self):
        if self.volume_node and self.volume_node.GetDisplayNode():
            self.window_level = (self.volume_node.GetDisplayNode().GetWindow(), self.volume_node.GetDisplayNode().GetLevel())

    def restore_window_level_settings(self):
        if self.volume_node and self.volume_node.GetDisplayNode():
            if self.window_level is not None:
                self.volume_node.GetDisplayNode().SetAutoWindowLevel(False)
                self.volume_node.GetDisplayNode().SetWindow(self.window_level[0])
                self.volume_node.GetDisplayNode().SetLevel(self.window_level[1])
            else:
                self.volume_node.GetDisplayNode().SetAutoWindowLevel(True)

    def store_segment_visiblity_states(self):
        if not self.segmentation_node or not self.segmentation_node.GetDisplayNode():
            return
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segmentation_node.GetDisplayNode().GetSegmentVisibility(segment_id)
            self.segment_visiblity_states[segment_id] = visibility

    def restore_segment_visiblity_states(self):
        if not self.segmentation_node:
            return
        for segment_id in self.segmentation_node.GetSegmentation().GetSegmentIDs():
            visibility = self.segment_visiblity_states.get(segment_id, True)
            self.segmentation_node.GetDisplayNode().SetSegmentVisibility(segment_id, visibility)

    def set_segmentation_and_mask_for_segmentation_editor(self):
        slicer.app.processEvents()
        self.selectParameterNode()
        self.segmentEditorWidget.setSegmentationNode(self.segmentation_node)
        self.segmentEditorWidget.setSourceVolumeNode(self.volume_node)
        segStatLogic = SegmentStatistics.SegmentStatisticsLogic()
        segStatLogic.getParameterNode().SetParameter("Segmentation", self.segmentation_node.GetID())
        segStatLogic.getParameterNode().SetParameter("LabelmapSegmentStatisticsPlugin.centroid_ras.enabled", str(True))
        segStatLogic.computeStatistics()
        stats = segStatLogic.getStatistics()
        self.pointListNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
        self.pointListNode.CreateDefaultDisplayNodes()
        self.pointListNode.SetName(f"Centroids_{self.caseId()}")
        markupsLogic = slicer.modules.markups.logic()
        for segmentId in stats["SegmentIDs"]:
            if self.segment_visiblity_states.get(segmentId, True):
                centroid_ras = stats[segmentId, "LabelmapSegmentStatisticsPlugin.centroid_ras"]
                markupsLogic.JumpSlicesToLocation(*centroid_ras, False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def cleanup(self):
        for sc in getattr(self, "_shortcuts", []):
            try:
                sc.setEnabled(False)
                sc.setParent(None)
            except Exception:
                pass
        self._shortcuts = []
        self.removeObservers()

    def exit(self):
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        try:
            self.setParameterNode(None)
            self.segmentEditorWidget.setSegmentationNode(None)
            self.segmentEditorWidget.removeViewObservations()
        except:
            pass
        # Scene is being wiped: our node handles are about to become stale.
        self.volume_node = None
        self.segmentation_node = None
        self.pointListNode = None
        self.loaded_markup_nodes = []
        self.loaded_model_nodes = []
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self._case_loaded = False

    def onSceneEndClose(self, caller, event):
        if self.parent.isEntered:
            self.initializeParameterNode()
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()

    def onSceneEndImport(self, caller, event):
        if self.parent.isEntered:
            self.selectParameterNode()
            self.segmentEditorWidget.updateWidgetFromMRML()
            self._enableMarkupsWidgetOptions()

    def initializeParameterNode(self):
        self.setParameterNode(self.logic.getParameterNode())
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        self._updatingGUIFromParameterNode = True
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        wasModified = self._parameterNode.StartModify()
        self._parameterNode.EndModify(wasModified)


class TavrWorkbenchLogic(ScriptedLoadableModuleLogic):
    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)


class TavrWorkbenchTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_TavrWorkbench1()

    def test_TavrWorkbench1(self):
        self.delayDisplay("Starting the test")
        self.delayDisplay('Test passed')