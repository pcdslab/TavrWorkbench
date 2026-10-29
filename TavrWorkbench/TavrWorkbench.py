"""
TavrWorkbench -- 3D Slicer scripted module
==========================================
One case list, two review modes:

* Segmentation  - Approve / Flag the mask (overall + per label), edit it with the embedded
                  Segment Editor, save the edited mask. Measurements are shown locked for context.
* Measurements  - correct Annulus / SOV / STJ contours with live area, perimeter and diameters,
                  view STJ / coronary heights on long-axis planes, Approve / Flag (overall + per item).

Both modes share case navigation, the comment, Save / Save & Next and the output folder.
Implementation lives in TavrWorkbenchLib/ (see its __init__.py for the module map).
"""
import logging
import os

import ctk
import qt
import slicer
import vtk
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from TavrWorkbenchLib.cases import (case_id_of, has_contours, has_measurements, is_file, is_image_path,
                                    measurement_rating_keys, read_data_map)
from TavrWorkbenchLib.constants import (CASE_MASK_FILE, LOG_FILE, MASK_STATUS_TEXT, MEAS_SEGMENTATION_OPACITY_3D,
                                        MEASUREMENT_KEY_TO_LABEL, MODE_MEASUREMENTS, MODE_SEGMENTATION, MODES,
                                        NOT_APPLICABLE_MARK, PENDING_MARK, RATING_ACCEPT, RATING_FLAG,
                                        RATING_TO_MARK, SEGMENTATION_LABELS, SELECTION_LABELS, SELECTIONS,
                                        SHORTCUT_ACCEPT, SHORTCUT_FLAG)
from TavrWorkbenchLib.measurement_editor import MeasurementEditor
from TavrWorkbenchLib.rating_table import (RatingTable, group_rating, make_decision_group, set_group_rating,
                                           uncheck_group)
from TavrWorkbenchLib.segmentation_editor import SegmentationController
from TavrWorkbenchLib.storage import OutputStore

# Suppress VTK warnings globally to prevent console flooding and UI freezing
vtk.vtkObject.GlobalWarningDisplayOff()

MODE_TITLES = {MODE_SEGMENTATION: "segmentation", MODE_MEASUREMENTS: "measurements"}


class TavrWorkbench(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("TavrWorkbench")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = ["Segmentations", "SegmentStatistics", "Markups"]
        self.parent.contributors = ["Mohammed Khubaib (Saeed Lab: Florida International University)"]
        self.parent.helpText = _("""
        A 3D Slicer extension for fast, structured review of TAVR CT segmentations and measurements.
        Switch between <b>Segmentation</b> review (approve / flag / edit masks) and <b>Measurements</b>
        review (correct annulus, SOV and STJ contours with live metrics, view heights) on the same case list.
        Shortcuts: Shift+A approve, Shift+F flag (current mode), Shift+Return save &amp; next.
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
        self.store = OutputStore()

        # case list
        self.samples = []
        self.case_flags = []          # per case: (has_measurements, has_contours)
        self.current_index = -1
        self._case_loaded = False
        self.mode = MODE_SEGMENTATION

        # current case
        self.volume_node = None
        self.mask_status = {}         # case_id -> key of MASK_STATUS_TEXT
        self.case_reviews = {}        # index -> review dict (in-memory, survives Prev/Next)
        self._views_reformatted = False

        # helpers (created in setup)
        self.seg = None
        self.meas = None
        self.segTable = None
        self.measTable = None
        self._shortcuts = []
        self._logger_handler = None

    # ==================================================================
    # Setup
    # ==================================================================
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/TavrWorkbench.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.segTable = RatingTable(self.ui.segReviewContainer, "Segmentation review", "Label")
        self.segTable.build(SEGMENTATION_LABELS)
        self.measTable = RatingTable(self.ui.measReviewContainer, "Measurement review", "Measurement")
        self.measTable.build([])
        self.ui.measItemsCollapsibleButton.setVisible(False)
        self.seg = SegmentationController(self.ui.segEditorContainer)
        self.meas = MeasurementEditor(on_update=self._refreshMeasurementLabels)

        self._setupCaseSection()
        self._setupModeSwitch()
        self._setupSegmentationPanel()
        self._setupMeasurementPanel()
        self._setupSharedControls()
        self._setupShortcuts()

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)

        self._setMode(MODE_SEGMENTATION)
        self._updateMeasurementPanel()
        self._updateSummary()

    def _setupCaseSection(self):
        ui = self.ui
        ui.mapPathEdit.filters = ctk.ctkPathLineEdit.Files
        ui.mapPathEdit.nameFilters = ["JSON files (*.json)"]
        ui.mapPathEdit.settingKey = "TavrWorkbench/mapFile"
        ui.outPathEdit.filters = ctk.ctkPathLineEdit.Dirs
        ui.outPathEdit.settingKey = "TavrWorkbench/outDir"
        self.store.set_root(self.outDir())
        ui.outPathEdit.connect("currentPathChanged(QString)", self._onOutputFolderChanged)
        ui.loadListButton.connect("clicked()", self.loadList)
        ui.caseCombo.connect("activated(int)", self.loadCase)
        ui.prevCaseButton.connect("clicked()", lambda: self.step(-1))
        ui.nextCaseButton.connect("clicked()", lambda: self.step(1))
        ui.nextUnreviewedButton.connect("clicked()", self.nextUnreviewed)

    def _setupModeSwitch(self):
        self.modeGroup = qt.QButtonGroup()
        self.modeGroup.setExclusive(True)
        self.modeGroup.addButton(self.ui.segModeButton, 0)
        self.modeGroup.addButton(self.ui.measModeButton, 1)
        self.modeGroup.connect("buttonClicked(int)", lambda i: self._setMode(MODES[i]))

    def _setupSegmentationPanel(self):
        ui = self.ui
        self.segDecisionGroup = make_decision_group(ui.segApproveRadio, ui.segFlagRadio)
        # Choosing the overall decision fills every label row; rows can then be adjusted individually.
        ui.segApproveRadio.connect("toggled(bool)", lambda on: on and self.segTable.set_all(RATING_ACCEPT))
        ui.segFlagRadio.connect("toggled(bool)", lambda on: on and self.segTable.set_all(RATING_FLAG))
        ui.segClearButton.connect("clicked()", self._clearSegmentationRatings)
        ui.saveMaskButton.connect("clicked()", self.saveMask)
        ui.showMeasurementsCheck.connect("toggled(bool)", self.meas.set_show_in_review)

    def _setupMeasurementPanel(self):
        ui = self.ui
        self.selRadios = {
            "annulus": ui.selAnnulusRadio, "sov": ui.selSovRadio, "stj": ui.selStjRadio,
            "stj_h": ui.selStjHRadio, "lch": ui.selLchRadio, "rch": ui.selRchRadio,
        }
        self.selGroup = qt.QButtonGroup()
        self.selGroup.setExclusive(True)
        for i, key in enumerate(SELECTIONS):
            self.selRadios[key].setText(SELECTION_LABELS[key])
            self.selGroup.addButton(self.selRadios[key], i)
        self.selGroup.connect("buttonClicked(int)", lambda i: self.meas.select(SELECTIONS[i]))

        ui.resampleButton.connect("clicked()", lambda: self.meas.resample(ui.nPtsSpinBox.value))
        ui.resetPlaneButton.connect("clicked()", self.meas.reset_plane)
        ui.alignViewButton.connect("clicked()", self.meas.align_view)
        ui.showAllHeightsCheck.connect("toggled(bool)", self.meas.set_show_all_heights)
        ui.showSegOutlineCheck.setText("Segmentation (outline + 3D)")
        ui.showSegOutlineCheck.setToolTip("Show the segmentation as an outline in the slice views and "
                                          f"at {MEAS_SEGMENTATION_OPACITY_3D:.0%} opacity in the 3D view")
        ui.showSegOutlineCheck.connect("toggled(bool)", lambda _on: self._applySegmentationDisplay())

        self.measDecisionGroup = make_decision_group(ui.measApproveRadio, ui.measFlagRadio)
        ui.measApproveRadio.connect("toggled(bool)", lambda on: on and self.measTable.set_all(RATING_ACCEPT))
        ui.measFlagRadio.connect("toggled(bool)", lambda on: on and self.measTable.set_all(RATING_FLAG))
        ui.measClearButton.connect("clicked()", self._clearMeasurementRatings)

    def _setupSharedControls(self):
        ui = self.ui
        ui.saveButton.connect("clicked()", lambda: self.saveCase(require_decision=False))
        ui.saveNextButton.connect("clicked()", self.saveAndNext)
        ui.openOutputButton.connect("clicked()", self.openOutputFolder)

    def _setupShortcuts(self):
        """Window-level shortcuts so the decision can be made while focus is in a slice/3D view."""
        for approve, flag in ((self.ui.segApproveRadio, self.ui.segFlagRadio),
                              (self.ui.measApproveRadio, self.ui.measFlagRadio)):
            approve.setText(f"✓ Approve ({SHORTCUT_ACCEPT})")
            flag.setText(f"⚑ Flag ({SHORTCUT_FLAG})")
        for key, rating in ((SHORTCUT_ACCEPT, RATING_ACCEPT), (SHORTCUT_FLAG, RATING_FLAG)):
            sc = qt.QShortcut(qt.QKeySequence(key), slicer.util.mainWindow())
            sc.setContext(qt.Qt.WindowShortcut)
            sc.connect("activated()", lambda r=rating: self._onDecisionShortcut(r))
            self._shortcuts.append(sc)

    # ==================================================================
    # Small helpers
    # ==================================================================
    def outDir(self):
        return str(self.ui.outPathEdit.currentPath or "")

    def caseId(self, idx=None):
        idx = self.current_index if idx is None else idx
        if idx is None or idx < 0 or idx >= len(self.samples):
            return ""
        return case_id_of(self.samples[idx], idx)

    def _caseHasMeasurements(self, idx):
        return 0 <= idx < len(self.case_flags) and self.case_flags[idx][0]

    def _isReviewed(self, idx, mode):
        cid = self.caseId(idx)
        if mode == MODE_SEGMENTATION:
            return bool(self.store.seg_rating(cid))
        return bool(self.store.meas_rating(cid))

    def _needsReview(self, idx, mode):
        if mode == MODE_MEASUREMENTS and not self._caseHasMeasurements(idx):
            return False
        return not self._isReviewed(idx, mode)

    def _decisionWidgets(self, mode=None):
        mode = mode or self.mode
        if mode == MODE_SEGMENTATION:
            return self.segDecisionGroup, self.ui.segApproveRadio, self.ui.segFlagRadio
        return self.measDecisionGroup, self.ui.measApproveRadio, self.ui.measFlagRadio

    # ==================================================================
    # Output folder / progress display
    # ==================================================================
    def _onOutputFolderChanged(self, path):
        self.store.set_root(path)
        self.refreshCombo()
        self._updateSummary()

    def openOutputFolder(self):
        if self.outDir() and os.path.isdir(self.outDir()):
            qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(self.outDir()))

    def refreshCombo(self):
        combo = self.ui.caseCombo
        combo.blockSignals(True)
        combo.clear()
        for i in range(len(self.samples)):
            cid = self.caseId(i)
            seg_mark = RATING_TO_MARK.get(self.store.seg_rating(cid), PENDING_MARK)
            if self._caseHasMeasurements(i):
                meas_mark = RATING_TO_MARK.get(self.store.meas_rating(cid), PENDING_MARK)
            else:
                meas_mark = NOT_APPLICABLE_MARK
            combo.addItem(f"{seg_mark}{meas_mark}  {cid}")
        if 0 <= self.current_index < combo.count:
            combo.setCurrentIndex(self.current_index)
        combo.blockSignals(False)

    def _updateSummary(self):
        total = len(self.samples)
        seg_done = sum(1 for i in range(total) if self._isReviewed(i, MODE_SEGMENTATION))
        meas_idx = [i for i in range(total) if self._caseHasMeasurements(i)]
        meas_done = sum(1 for i in meas_idx if self._isReviewed(i, MODE_MEASUREMENTS))
        self.ui.summarySegLabel.setText(f"Segmentation: {seg_done} / {total} reviewed, {total - seg_done} pending")
        self.ui.summaryMeasLabel.setText(f"Measurements: {meas_done} / {len(meas_idx)} reviewed, "
                                         f"{len(meas_idx) - meas_done} pending")
        if total and self.current_index >= 0:
            self.ui.statusLabel.setText(f"<b>Case {self.current_index + 1} / {total}:</b> {self.caseId()}")
        else:
            self.ui.statusLabel.setText("No case list loaded")

    # ==================================================================
    # Mode switching
    # ==================================================================
    def _setMode(self, mode):
        self.mode = mode
        is_seg = mode == MODE_SEGMENTATION
        self.ui.segModeButton.setChecked(is_seg)
        self.ui.measModeButton.setChecked(not is_seg)
        self.ui.segPanel.setVisible(is_seg)
        self.ui.measPanel.setVisible(not is_seg)
        if not is_seg:
            self.seg.deactivate_effect()  # no accidental painting while dragging contour points
        self._applyModeToScene()

    def _applyModeToScene(self):
        measuring = self.mode == MODE_MEASUREMENTS and self.meas.has_contours()
        self._applySegmentationDisplay()
        self.meas.set_mode_active(self.mode == MODE_MEASUREMENTS)
        if measuring:
            self._views_reformatted = True
        elif self._views_reformatted:
            self._standardViews()

    def _applySegmentationDisplay(self):
        """Segmentation mode: normal display (3D opacity back to full).
        Measurements mode: hidden, or - with the checkbox - outline in the slices + see-through 3D."""
        is_seg = self.mode == MODE_SEGMENTATION
        if is_seg:
            self.seg.set_display(outline_only=False, visible=True, opacity_3d=None)
            self.seg.set_opacity_3d(1.0)
        else:
            show = bool(self.ui.showSegOutlineCheck.checked)
            self.seg.set_display(outline_only=True, visible=show,
                                 opacity_3d=MEAS_SEGMENTATION_OPACITY_3D if show else None)

    def _standardViews(self):
        """Undo the contour-plane reformatting: four-up, axial / sagittal / coronal, fitted."""
        lm = slicer.app.layoutManager()
        lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        for name, orientation in (("Red", "Axial"), ("Yellow", "Sagittal"), ("Green", "Coronal")):
            widget = lm.sliceWidget(name)
            if widget is None:
                continue
            widget.mrmlSliceNode().SetOrientation(orientation)
            widget.sliceLogic().FitSliceToAll()
        self._views_reformatted = False

    def _onDecisionShortcut(self, rating):
        if not self.parent.isEntered or not self._case_loaded:
            return
        _group, approve, flag = self._decisionWidgets()
        if approve.enabled:
            (approve if rating == RATING_ACCEPT else flag).setChecked(True)

    # ==================================================================
    # Case list
    # ==================================================================
    def loadList(self):
        mp = str(self.ui.mapPathEdit.currentPath or "")
        if not mp or not os.path.isfile(mp):
            slicer.util.errorDisplay("Select the data-map .json file first.")
            return
        if not self.outDir():
            slicer.util.warningDisplay("No output folder selected yet - choose one before saving.")
        if not self._confirmLeaveCase():
            return
        try:
            usable, skipped = read_data_map(mp)
        except Exception as e:
            slicer.util.errorDisplay(f"Could not parse data-map JSON:\n{e}")
            return
        if not usable:
            slicer.util.errorDisplay("No usable cases found in this data map "
                                     "(every 'image' path is missing or has an unsupported extension).")
            return
        if skipped:
            print(f"[TavrWorkbench] Skipped {skipped} sample(s) with missing/unsupported image path.")

        self._clearCaseNodes()
        self.samples = usable
        self.case_flags = [(has_measurements(s), has_contours(s)) for s in usable]
        self.current_index = -1
        self._case_loaded = False
        self.case_reviews = {}
        self.mask_status = {}

        keys = measurement_rating_keys(usable)
        self.measTable.build([MEASUREMENT_KEY_TO_LABEL.get(k, k) for k in keys])
        self.ui.measItemsCollapsibleButton.setVisible(bool(keys))

        self._setupLogger(mp)
        self.store.reload()
        self.refreshCombo()

        # Resume at the first case still pending in the current mode
        start = next((i for i in range(len(usable)) if self._needsReview(i, self.mode)), 0)
        msg = f"Loaded {len(usable)} cases"
        if skipped:
            msg += f" ({skipped} skipped: missing/unsupported image)"
        slicer.util.showStatusMessage(msg, 4000)
        self.loadCase(start)

    def _setupLogger(self, map_path):
        logger = logging.getLogger("TavrWorkbench")
        logger.setLevel(logging.DEBUG)
        if self._logger_handler is not None:
            logger.removeHandler(self._logger_handler)
            self._logger_handler.close()
            self._logger_handler = None
        log_dir = self.outDir() if self.outDir() and os.path.isdir(self.outDir()) else os.path.dirname(map_path)
        try:
            handler = logging.FileHandler(os.path.join(log_dir, LOG_FILE))
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
            logger.addHandler(handler)
            self._logger_handler = handler
            logger.info(f"Loaded data map {map_path}")
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not create log file: {e}")

    # ==================================================================
    # Navigation
    # ==================================================================
    def step(self, d):
        if not self.samples:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        target = self.current_index + d
        if target < 0:
            slicer.util.warningDisplay("Already at the first case.")
            return
        if target >= len(self.samples):
            slicer.util.warningDisplay("Already at the last case.")
            return
        self.loadCase(target)

    def nextUnreviewed(self):
        n = len(self.samples)
        if not n:
            return
        for k in range(1, n + 1):
            j = (self.current_index + k) % n
            if self._needsReview(j, self.mode):
                return self.loadCase(j)
        slicer.util.infoDisplay(f"All cases have been reviewed for {MODE_TITLES[self.mode]}.")

    def _confirmLeaveCase(self):
        """Ask about unsaved contour edits. Returns False if the user cancels."""
        if not (self._case_loaded and self.meas.is_dirty()):
            return True
        ans = qt.QMessageBox.question(slicer.util.mainWindow(), "Unsaved contour edits",
                                      "Save contour edits for this case first?",
                                      qt.QMessageBox.Yes | qt.QMessageBox.No | qt.QMessageBox.Cancel)
        if ans == qt.QMessageBox.Cancel:
            return False
        if ans == qt.QMessageBox.Yes:
            return self.saveCase(require_decision=False)
        return True

    def loadCase(self, idx):
        if not self.samples:
            return
        idx = max(0, min(len(self.samples) - 1, int(idx)))
        if self._case_loaded:
            if not self._confirmLeaveCase():
                self.refreshCombo()  # put the combo back on the current case
                return
            self._cacheReview()      # keep in memory so Prev/Next doesn't lose ratings
        self.current_index = idx
        self._loadCaseData()
        self._case_loaded = True
        self._restoreReview(idx)
        self._updateMeasurementPanel()
        self._applyModeToScene()
        self.ui.saveLabel.setText("")
        self.refreshCombo()
        self._updateSummary()

    # ==================================================================
    # Case data (MRML nodes)
    # ==================================================================
    def _clearCaseNodes(self):
        """Remove every MRML node belonging to the currently loaded case."""
        self.seg.store_visibility()
        nodes = set(self.seg.release())
        if self.volume_node is not None:
            nodes.add(self.volume_node)
        for node in nodes:
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: failed removing node: {e}")
        self.meas.clear()
        self.volume_node = None

    def _resolveLabelPath(self, sample, cid):
        """Edited mask in the output folder wins over the original label."""
        edited = self.store.edited_mask_path(cid)
        if edited:
            return edited, True
        label = sample.get("label") or ""
        if is_image_path(label) and is_file(label):
            return label, False
        return "", False

    def _loadCaseData(self):
        self._clearCaseNodes()
        sample = self.samples[self.current_index]
        cid = self.caseId()
        image_path = sample.get("image", "")
        print(f"[TavrWorkbench] Loading case {cid} ({self.current_index + 1}/{len(self.samples)}): {image_path}")
        label_path, from_saved_mask = self._resolveLabelPath(sample, cid)

        lm = slicer.app.layoutManager()
        lm.setRenderPaused(True)
        try:
            try:
                self.volume_node = slicer.util.loadVolume(image_path)
            except Exception as e:
                print(f"[TavrWorkbench] ERROR loading volume {image_path}: {e}")
                self.volume_node = None
            if self.volume_node is None:
                slicer.util.errorDisplay(f"Could not load volume for case {cid}:\n{image_path}")
                return False
            # Window/level is left exactly as Slicer loads the CT (no override).
            slicer.util.setSliceViewerLayers(background=self.volume_node, fit=False)
            self._loadSegmentation(sample, cid, label_path, from_saved_mask)
            self.meas.load(sample, lambda plane: self.store.find_saved_contour(cid, plane))
        finally:
            lm.setRenderPaused(False)
            slicer.app.processEvents()

        for name in lm.sliceViewNames():
            try:
                lm.sliceWidget(name).sliceLogic().FitSliceToAll()
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: FitSliceToAll failed for {name}: {e}")
        self.seg.jump_to_centroids()
        return True

    def _loadSegmentation(self, sample, cid, label_path, from_saved_mask):
        node = None
        if label_path:
            node = self.seg.load(label_path)
            if node:
                self.mask_status[cid] = 3 if from_saved_mask else 2
            else:
                self.mask_status[cid] = 1
                print(f"[TavrWorkbench] WARNING: segmentation could not be loaded for case {cid}: {label_path}")
        else:
            self.mask_status[cid] = 1 if sample.get("label") else 0
            logging.getLogger("TavrWorkbench").info(f"Case {cid}: no usable segmentation label found")
        if node is None:
            node = self.seg.create_empty(f"Segmentation_{cid}", self.volume_node)
        try:
            self.seg.attach(node, self.volume_node)
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not initialize segment editor for case {cid}: {e}")

    # ==================================================================
    # Measurement panel
    # ==================================================================
    def _updateMeasurementPanel(self):
        has_contours = self.meas.has_contours()
        self.ui.measUnavailableLabel.setVisible(self._case_loaded and not has_contours)
        self.ui.measViewGroupBox.setEnabled(has_contours)
        self.ui.measEditGroupBox.setEnabled(has_contours)
        self.ui.measDecisionWidget.setEnabled(self._caseHasMeasurements(self.current_index))
        available = self.meas.available_selections()
        for key, radio in self.selRadios.items():
            radio.setEnabled(key in available)
        if self.meas.selection in self.selRadios:
            self.selRadios[self.meas.selection].setChecked(True)
        self._refreshMeasurementLabels()

    def _refreshMeasurementLabels(self):
        self.ui.metricsLabel.setText(self.meas.info_html())
        self.ui.heightsLabel.setText(self.meas.heights_html())

    # ==================================================================
    # Ratings
    # ==================================================================
    def _clearSegmentationRatings(self):
        uncheck_group(self.segDecisionGroup)
        self.segTable.clear()

    def _clearMeasurementRatings(self):
        uncheck_group(self.measDecisionGroup)
        self.measTable.clear()

    def _currentReview(self):
        return {
            "overall": group_rating(self.segDecisionGroup),
            "segmentation": self.segTable.ratings(),
            "measurements_overall": group_rating(self.measDecisionGroup),
            "measurements": self.measTable.ratings(),
            "comment": self.ui.commentEdit.toPlainText(),
        }

    def _cacheReview(self):
        if self.current_index < 0:
            return None
        review = self._currentReview()
        self.case_reviews[self.current_index] = review
        return review

    def _restoreReview(self, idx):
        review = self.case_reviews.get(idx)
        if review is None:
            review = self.store.read_review(self.caseId(idx))
            if review is not None:
                self.case_reviews[idx] = review
        review = review or {}
        meas_overall = review.get("measurements_overall") or self.store.meas_rating(self.caseId(idx))
        # Setting the overall decision auto-fills the rows; the stored rows then override that.
        set_group_rating(self.segDecisionGroup, review.get("overall"))
        self.segTable.set_ratings(review.get("segmentation"))
        set_group_rating(self.measDecisionGroup, meas_overall)
        self.measTable.set_ratings(review.get("measurements"))
        self.ui.commentEdit.setPlainText(review.get("comment", ""))

    # ==================================================================
    # Saving
    # ==================================================================
    def saveCase(self, require_decision=False):
        """Persist the current case. With require_decision, the current mode's decision must be set."""
        if not self._case_loaded or self.current_index < 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return False
        if not self.outDir():
            slicer.util.errorDisplay("Select an output folder first.")
            return False

        review = self._cacheReview()
        seg_decision = review["overall"]
        meas_decision = review["measurements_overall"]
        contours_dirty = self.meas.is_dirty()
        if require_decision:
            decided = seg_decision if self.mode == MODE_SEGMENTATION else meas_decision
            if not decided:
                slicer.util.warningDisplay(f"Please choose Approve or Flag for the {MODE_TITLES[self.mode]} "
                                           "before saving.")
                return False
        elif not (seg_decision or meas_decision or contours_dirty):
            slicer.util.warningDisplay("Nothing to save yet: choose Approve or Flag, or edit a contour.")
            return False

        cid = self.caseId()
        sample = self.samples[self.current_index]
        saved = []
        try:
            if self.meas.has_contours() and (contours_dirty or meas_decision):
                self.store.ensure_case_dir(cid)
                self.meas.save_nodes(lambda plane, key: self.store.contour_path(cid, plane, key))
                self.store.upsert_measurements(cid, self.meas.metrics_rows(), self.meas.dirty)
                self.meas.mark_saved()
                saved.append("contours")
            if meas_decision:
                self.store.set_meas_decision(cid, meas_decision)
            if seg_decision or cid in self.store.seg_status:
                self.store.set_seg_decision(cid, seg_decision)
            self.store.write_review(cid, review)
            self.store.upsert_annotation(cid, sample, review,
                                         MASK_STATUS_TEXT.get(self.mask_status.get(cid, 0), "Unknown"))
            self.store.dump()
            saved.append("review")
        except Exception as e:
            slicer.util.errorDisplay(f"Could not save case {cid}:\n{e}")
            return False

        self.ui.saveLabel.setText(f"Saved {' + '.join(saved)} for case {cid} to {self.store.case_dir(cid)}")
        slicer.util.showStatusMessage(f"Saved case {cid}", 3000)
        self.refreshCombo()
        self._updateSummary()
        return True

    def saveAndNext(self):
        nothing_to_review = self.mode == MODE_MEASUREMENTS and not self._caseHasMeasurements(self.current_index)
        if not nothing_to_review and not self.saveCase(require_decision=True):
            return
        if self.current_index + 1 < len(self.samples):
            self.loadCase(self.current_index + 1)
        elif not any(self._needsReview(i, self.mode) for i in range(len(self.samples))):
            slicer.util.infoDisplay(f"All cases have been reviewed for {MODE_TITLES[self.mode]}.", "Finished")
        else:
            self.nextUnreviewed()

    def saveMask(self):
        """Save the (possibly edited) segmentation to <output>/<case_id>/segmentation.seg.nrrd.
        The original label file is never touched; the edited copy is preferred when the case is re-opened."""
        if not self._case_loaded:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if not self.outDir():
            slicer.util.warningDisplay("No output folder is set.")
            return
        if self.seg.node is None:
            slicer.util.warningDisplay("No segmentation node found to save.")
            return
        cid = self.caseId()
        self.store.ensure_case_dir(cid)
        path = self.store.case_path(cid, CASE_MASK_FILE)
        if not slicer.util.saveNode(self.seg.node, path):
            slicer.util.errorDisplay(f"Could not save segmentation to:\n{path}")
            return
        self.mask_status[cid] = 3
        self.store.mark_mask_edited(cid)
        self.store.dump()
        slicer.util.infoDisplay(f"Segmentation saved successfully as:\n{path}")

    # ==================================================================
    # Lifecycle
    # ==================================================================
    def enter(self):
        self.seg.refresh()

    def cleanup(self):
        for sc in self._shortcuts:
            try:
                sc.setEnabled(False)
                sc.setParent(None)
            except Exception:
                pass
        self._shortcuts = []
        if self.meas is not None:
            self.meas.forget()
        self.removeObservers()

    def onSceneStartClose(self, caller, event):
        # Scene is being wiped: node handles are about to become stale.
        self.seg.on_scene_start_close()
        self.meas.forget()
        self.volume_node = None
        self._case_loaded = False
        self._refreshMeasurementLabels()

    def onSceneEndClose(self, caller, event):
        if self.parent.isEntered:
            self.seg.refresh()

    def onSceneEndImport(self, caller, event):
        if self.parent.isEntered:
            self.seg.refresh()

    def onReload(self):
        """Developer 'Reload': also re-import the helper package, not just this file."""
        import sys
        for name in [n for n in sys.modules if n == "TavrWorkbenchLib" or n.startswith("TavrWorkbenchLib.")]:
            del sys.modules[name]
        ScriptedLoadableModuleWidget.onReload(self)


class TavrWorkbenchLogic(ScriptedLoadableModuleLogic):
    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)


class TavrWorkbenchTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_ContourMetrics()

    def test_ContourMetrics(self):
        """Circle of radius 10 mm: area ≈ 314, max ≈ min ≈ 20, resampling keeps it."""
        import numpy as np
        from TavrWorkbenchLib.geometry import compute_metrics, resample_closed

        self.delayDisplay("Checking contour metrics")
        t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
        circle = np.column_stack([10 * np.cos(t), 10 * np.sin(t), np.full_like(t, 5.0)])
        m = compute_metrics(circle)
        self.assertAlmostEqual(m["area"], np.pi * 100, delta=1.0)
        self.assertAlmostEqual(m["max_d"], 20.0, delta=0.1)
        self.assertAlmostEqual(m["min_d"], 20.0, delta=0.1)
        self.assertEqual(len(resample_closed(circle, 12)), 12)
        self.delayDisplay("Test passed")
