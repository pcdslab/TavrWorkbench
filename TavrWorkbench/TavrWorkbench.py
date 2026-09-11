import logging
import os
import vtk
import pathlib
from pathlib import Path
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import ctk
import qt
from datetime import datetime
import SegmentStatistics
import logging
import json

# Suppress VTK warnings globally to prevent console flooding and UI freezing
vtk.vtkObject.GlobalWarningDisplayOff()

try:
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk
except:
    slicer.util.pip_install('pandas')
    slicer.util.pip_install('numpy')
    slicer.util.pip_install('SimpleITK')
    import pandas as pd
    import numpy as np
    import SimpleITK as sitk

import warnings
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Review constants
# ---------------------------------------------------------------------------
RATING_ACCEPTABLE = "acceptable"
RATING_MINOR = "minor"
RATING_NOT_ACCEPTABLE = "not_acceptable"
RATING_NONE = ""

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


class TavrWorkbench(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("TavrWorkbench")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Mohammed Khubaib (Saeed Lab: Florida International University)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
        A 3D Slicer extension for fast, structured review of TAVR CT segmentations and measurements.
        See more information in <a href="https://github.com/organization/projectname#TavrWorkbench">module documentation</a>.
        """)
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
        This 3D Slicer module was developed by <a href="https://github.com/Mohammed-Khubaib">Mohammed Khubaib</a>, M.S. Computer Engineering, Florida International University, as part of the <a href="https://pcdslab.github.io/">Saeed Lab</a> under the supervision of <a href="https://pcdslab.github.io/team/Fahad-Saeed">Dr. Fahad Saeed</a> and <a href="https://www.cis.fiu.edu/faculty-staff/kaoutar-ben-ahmed/">Dr. Kaoutar Ben Ahmed</a>.""")

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#


def registerSampleData():
    """Add data sets to Sample Data module."""
    # It is always recommended to provide sample data for users to make it easy to try the module,
    # but if no sample data is available then this method (and associated startupCompeted signal connection) can be removed.

    import SampleData

    iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")

    # To ensure that the source code repository remains small (can be downloaded and installed quickly)
    # it is recommended to store data sets that are larger than a few MB in a Github release.

    SampleData.SampleDataLogic.registerCustomSampleDataCategory("TavrWorkbench", title=_("TavrWorkbench"))

    # TODO: replace these placeholder sample data entries with real sample datasets for TavrWorkbench,
    # or remove this function (and the startupCompleted connection above) entirely if no sample data
    # is provided.

    # TavrWorkbench1
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category="TavrWorkbench",
        sampleName="TavrWorkbench1",
        # Thumbnail should have size of approximately 260x280 pixels and stored in Resources/Icons folder.
        # It can be created by Screen Capture module, "Capture all views" option enabled, "Number of images" set to "Single".
        thumbnailFileName=os.path.join(iconsPath, "TavrWorkbench1.png"),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        fileNames="TavrWorkbench1.nrrd",
        # Checksum to ensure file integrity. Can be computed by this command:
        #  import hashlib; print(hashlib.sha256(open(filename, "rb").read()).hexdigest())
        checksums="SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        # This node name will be used when the data set is loaded
        nodeNames="TavrWorkbench1",
    )

    # TavrWorkbench2
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category="TavrWorkbench",
        sampleName="TavrWorkbench2",
        thumbnailFileName=os.path.join(iconsPath, "TavrWorkbench2.png"),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        fileNames="TavrWorkbench2.nrrd",
        checksums="SHA256:1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        # This node name will be used when the data set is loaded
        nodeNames="TavrWorkbench2",
    )



class TavrWorkbenchWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        self.volume_node = None
        self.segmentation_node = None
        self.nifti_files = []
        self.segmentation_files = []
        self.directory = None
        self.current_index = 0
        self.likert_scores = []
        self.n_files = 0
        self.seg_mask_status = []
        self.with_mapper_flag = False
        self.id_subs = []
        self.id_subs_checked = []
        self.unique_case_flag = False
        self.finish_flag = False
        self.pointListNode = None
        self.window_level = None
        self.segment_visiblity_states = {}
        self.json_mode = False
        self.markup_paths_per_case = []
        self.case_ids = []
        self.loaded_markup_nodes = []
        self.json_manifest_dir = None
        self.annulus_contour_node = None
        self.contour_nodes_by_label = {}

        # ---- Centerline model (surface.vtp / centerline.vtp) support ----
        self.centerline_model_paths_per_case = []
        self.loaded_model_nodes = []

        # ---- New review state ----
        self.overall_button_group = None
        self.seg_button_groups = {}
        self.meas_button_groups = {}
        self.case_reviews = {}
        self.active_measurement_keys = []
        
        # Summary tracking
        self.total_samples_in_dataset = 0
        self.reviewed_count = 0
        self.pending_count = 0

    def setup(self):
        import qSlicerSegmentationsModuleWidgetsPythonQt
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(self.resourcePath('UI/TavrWorkbench.ui'))

        inputCollapsibleButton = ctk.ctkCollapsibleButton()
        inputCollapsibleButton.text = "Input"
        self.layout.addWidget(inputCollapsibleButton)
        inputLayout = qt.QVBoxLayout(inputCollapsibleButton)

        modeLayout = qt.QHBoxLayout()
        self.inputModeDirectory = qt.QRadioButton("Directory")
        self.inputModeJson = qt.QRadioButton("JSON Manifest")
        self.inputModeDirectory.setChecked(True)
        modeLayout.addWidget(self.inputModeDirectory)
        modeLayout.addWidget(self.inputModeJson)
        modeLayout.addStretch(1)
        inputLayout.addLayout(modeLayout)

        self.directoryInputWidget = qt.QWidget()
        directoryFormLayout = qt.QFormLayout(self.directoryInputWidget)
        self.atlasDirectoryButton = ctk.ctkDirectoryButton()
        directoryFormLayout.addRow("Directory: ", self.atlasDirectoryButton)
        inputLayout.addWidget(self.directoryInputWidget)

        self.jsonInputWidget = qt.QWidget()
        jsonFormLayout = qt.QFormLayout(self.jsonInputWidget)
        self.jsonManifestPathEdit = ctk.ctkPathLineEdit()
        self.jsonManifestPathEdit.filters = ctk.ctkPathLineEdit.Files
        self.jsonManifestPathEdit.nameFilters = ["JSON files (*.json)"]
        jsonFormLayout.addRow("Manifest JSON: ", self.jsonManifestPathEdit)
        inputLayout.addWidget(self.jsonInputWidget)

        self.directoryInputWidget.setVisible(True)
        self.jsonInputWidget.setVisible(False)

        self.inputModeDirectory.toggled.connect(self.onInputModeDirectoryToggled)
        self.inputModeJson.toggled.connect(self.onInputModeJsonToggled)
        self.jsonManifestPathEdit.currentPathChanged.connect(self.onJsonManifestChanged)

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
        self.atlasDirectoryButton.directoryChanged.connect(self.onAtlasDirectoryChanged)
        self.ui.save_and_next.connect('clicked(bool)', self.save_and_next_clicked)
        self.ui.previous_case.connect('clicked(bool)', self.previous_case_clicked)
        self.ui.skip_case.connect('clicked(bool)', self.skip_case_clicked)
        self.ui.clear_overall.connect('clicked(bool)', self.clear_overall_clicked)
        self.ui.overwrite_mask.connect('clicked(bool)', self.overwrite_mask_clicked)

        self.overall_button_group = qt.QButtonGroup()
        self.overall_button_group.addButton(self.ui.radio_acceptable, 0)
        self.overall_button_group.addButton(self.ui.radio_minor, 1)
        self.overall_button_group.addButton(self.ui.radio_not_acceptable, 2)

        self.ui.radio_acceptable.toggled.connect(lambda checked: self._onOverallToggled(RATING_ACCEPTABLE, checked))
        self.ui.radio_minor.toggled.connect(lambda checked: self._onOverallToggled(RATING_MINOR, checked))
        self.ui.radio_not_acceptable.toggled.connect(lambda checked: self._onOverallToggled(RATING_NOT_ACCEPTABLE, checked))

        self._buildSegmentationReviewTable()
        self.ui.measReviewContainer.setVisible(False)

        self._createSegmentEditorWidget_()
        self._createMarkupWidget_()

    def _buildSegmentationReviewTable(self):
        container = self.ui.segReviewContainer
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        groupBox = qt.QGroupBox("Segmentation Review")
        grid = qt.QGridLayout(groupBox)

        grid.addWidget(qt.QLabel("<b>Label</b>"), 0, 0)
        grid.addWidget(qt.QLabel("<b>✓</b>"), 0, 1, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>△</b>"), 0, 2, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>✕</b>"), 0, 3, qt.Qt.AlignCenter)

        for row_idx, label in enumerate(SEGMENTATION_LABELS, start=1):
            grid.addWidget(qt.QLabel(label), row_idx, 0)

            bg = qt.QButtonGroup()
            for col_idx, rating in enumerate([RATING_ACCEPTABLE, RATING_MINOR, RATING_NOT_ACCEPTABLE], start=1):
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
            return

        container.setVisible(True)
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        groupBox = qt.QGroupBox("Measurement Review")
        grid = qt.QGridLayout(groupBox)

        grid.addWidget(qt.QLabel("<b>Measurement</b>"), 0, 0)
        grid.addWidget(qt.QLabel("<b>✓</b>"), 0, 1, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>△</b>"), 0, 2, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>✕</b>"), 0, 3, qt.Qt.AlignCenter)

        for row_idx, key in enumerate(measurement_keys, start=1):
            display = MEASUREMENT_KEY_TO_LABEL.get(key, key)
            grid.addWidget(qt.QLabel(display), row_idx, 0)

            bg = qt.QButtonGroup()
            for col_idx, rating in enumerate([RATING_ACCEPTABLE, RATING_MINOR, RATING_NOT_ACCEPTABLE], start=1):
                rb = qt.QRadioButton()
                bg.addButton(rb, col_idx)
                grid.addWidget(rb, row_idx, col_idx, qt.Qt.AlignCenter)
            self.meas_button_groups[display] = bg

        layout.addWidget(groupBox)
        self.active_measurement_keys = measurement_keys

    def _onOverallToggled(self, rating, checked):
        if not checked:
            return
        
        for label, bg in self.seg_button_groups.items():
            if rating == RATING_ACCEPTABLE:
                bg.button(1).setChecked(True)
            elif rating == RATING_MINOR:
                bg.button(2).setChecked(True)
            elif rating == RATING_NOT_ACCEPTABLE:
                bg.button(3).setChecked(True)
                
        for display, bg in self.meas_button_groups.items():
            if rating == RATING_ACCEPTABLE:
                bg.button(1).setChecked(True)
            elif rating == RATING_MINOR:
                bg.button(2).setChecked(True)
            elif rating == RATING_NOT_ACCEPTABLE:
                bg.button(3).setChecked(True)

    def _resetReviewUI(self):
        if self.overall_button_group:
            self.overall_button_group.setExclusive(False)
            btn = self.overall_button_group.checkedButton()
            if btn:
                btn.setChecked(False)
            self.overall_button_group.setExclusive(True)
        
        for bg in self.seg_button_groups.values():
            bg.setExclusive(False)
            btn = bg.checkedButton()
            if btn:
                btn.setChecked(False)
            bg.setExclusive(True)
        
        for bg in self.meas_button_groups.values():
            bg.setExclusive(False)
            btn = bg.checkedButton()
            if btn:
                btn.setChecked(False)
            bg.setExclusive(True)
        
        self.ui.comment.setPlainText("")

    def _getOverallRating(self):
        if self.ui.radio_acceptable.isChecked():
            return RATING_ACCEPTABLE
        if self.ui.radio_minor.isChecked():
            return RATING_MINOR
        if self.ui.radio_not_acceptable.isChecked():
            return RATING_NOT_ACCEPTABLE
        return RATING_NONE

    def _getSegRatings(self):
        result = {}
        for label, bg in self.seg_button_groups.items():
            checked_id = bg.checkedId()
            if checked_id == 1:
                result[label] = RATING_ACCEPTABLE
            elif checked_id == 2:
                result[label] = RATING_MINOR
            elif checked_id == 3:
                result[label] = RATING_NOT_ACCEPTABLE
            else:
                result[label] = RATING_NONE
        return result

    def _getMeasRatings(self):
        result = {}
        for display, bg in self.meas_button_groups.items():
            checked_id = bg.checkedId()
            if checked_id == 1:
                result[display] = RATING_ACCEPTABLE
            elif checked_id == 2:
                result[display] = RATING_MINOR
            elif checked_id == 3:
                result[display] = RATING_NOT_ACCEPTABLE
            else:
                result[display] = RATING_NONE
        return result

    def _saveCurrentReview(self):
        self.case_reviews[self.current_index] = {
            "overall": self._getOverallRating(),
            "segmentation": self._getSegRatings(),
            "measurements": self._getMeasRatings(),
            "comment": self.ui.comment.toPlainText(),
        }

    def _restoreReview(self, index):
        review = self.case_reviews.get(index)
        if review is None:
            self._resetReviewUI()
            return
        
        has_data = False
        if review.get("overall", RATING_NONE) != RATING_NONE:
            has_data = True
        if any(v != RATING_NONE for v in review.get("segmentation", {}).values()):
            has_data = True
        if any(v != RATING_NONE for v in review.get("measurements", {}).values()):
            has_data = True
        
        if not has_data:
            self._resetReviewUI()
            return
        
        ov = review.get("overall", RATING_NONE)
        self.ui.radio_acceptable.setChecked(ov == RATING_ACCEPTABLE)
        self.ui.radio_minor.setChecked(ov == RATING_MINOR)
        self.ui.radio_not_acceptable.setChecked(ov == RATING_NOT_ACCEPTABLE)
        
        seg = review.get("segmentation", {})
        for label, bg in self.seg_button_groups.items():
            val = seg.get(label, RATING_NONE)
            bg.setExclusive(False)
            for btn in bg.buttons():
                btn.setChecked(False)
            if val == RATING_ACCEPTABLE:
                bg.button(1).setChecked(True)
            elif val == RATING_MINOR:
                bg.button(2).setChecked(True)
            elif val == RATING_NOT_ACCEPTABLE:
                bg.button(3).setChecked(True)
            bg.setExclusive(True)
        
        meas = review.get("measurements", {})
        for display, bg in self.meas_button_groups.items():
            val = meas.get(display, RATING_NONE)
            bg.setExclusive(False)
            for btn in bg.buttons():
                btn.setChecked(False)
            if val == RATING_ACCEPTABLE:
                bg.button(1).setChecked(True)
            elif val == RATING_MINOR:
                bg.button(2).setChecked(True)
            elif val == RATING_NOT_ACCEPTABLE:
                bg.button(3).setChecked(True)
            bg.setExclusive(True)
        
        self.ui.comment.setPlainText(review.get("comment", ""))

    def _loadReviewsFromCSV(self):
        csv_path = self.joinpath(self.directory, "annotations.csv")
        if not os.path.exists(csv_path):
            return
        
        try:
            df = pd.read_csv(csv_path)
            
            file_to_index = {}
            for idx, file_path in enumerate(self.nifti_files):
                file_to_index[file_path] = idx
            
            for _, row in df.iterrows():
                file_path = row.get('file', '')
                if file_path in file_to_index:
                    idx = file_to_index[file_path]
                    review = {
                        "overall": RATING_NONE,
                        "segmentation": {},
                        "measurements": {},
                        "comment": row.get('comment', '')
                    }
                    
                    for label in SEGMENTATION_LABELS:
                        if label in row:
                            rating_str = row[label]
                            if rating_str == "✓ Acceptable":
                                review["segmentation"][label] = RATING_ACCEPTABLE
                            elif rating_str == "△ Minor correction":
                                review["segmentation"][label] = RATING_MINOR
                            elif rating_str == "✕ Not acceptable":
                                review["segmentation"][label] = RATING_NOT_ACCEPTABLE
                    
                    for meas in ALL_MEASUREMENT_COLUMNS:
                        if meas in row:
                            rating_str = row[meas]
                            if rating_str == "✓ Acceptable":
                                review["measurements"][meas] = RATING_ACCEPTABLE
                            elif rating_str == "△ Minor correction":
                                review["measurements"][meas] = RATING_MINOR
                            elif rating_str == "✕ Not acceptable":
                                review["measurements"][meas] = RATING_NOT_ACCEPTABLE
                    
                    self.case_reviews[idx] = review
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: Could not load reviews from CSV: {e}")

    def _updateSummary(self):
        self.ui.summaryTotal.setText(f"Total Samples in Dataset: {self.total_samples_in_dataset}")
        self.ui.summaryReviewed.setText(f"Reviewed: {self.reviewed_count}")
        self.ui.summaryPending.setText(f"Pending: {self.pending_count}")

    def _rating_to_str(self, rating):
        return {
            RATING_ACCEPTABLE: "✓ Acceptable",
            RATING_MINOR: "△ Minor correction",
            RATING_NOT_ACCEPTABLE: "✕ Not acceptable",
            RATING_NONE: "",
        }.get(rating, "")

    def _numerical_status_to_str(self, status):
        return {0: "No mask found", 1: "Cannot load mask", 2: "Mask loaded, no edits", 3: "Mask edited"}.get(status, "Unknown")

    def previous_case_clicked(self):
        if self.n_files == 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if self.current_index <= 0:
            slicer.util.warningDisplay("Already at the first case.")
            return

        self._saveCurrentReview()
        self.current_index -= 1
        self.finish_flag = False

        if self.json_mode:
            self.load_json_case()
        else:
            self.load_nifti_file(self.unique_case_flag)

        self._restoreReview(self.current_index)
        self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))

    def clear_overall_clicked(self):
        """Clear all radio buttons: Overall, Segmentation, and Measurement."""
        self._resetReviewUI()

    def skip_case_clicked(self):
        """Skip the current case without saving anything and move to the next case."""
        if self.n_files == 0:
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        
        if self.current_index >= self.n_files - 1:
            slicer.util.warningDisplay("Already at the last case.")
            return
        
        if self.json_mode:
            nodes_to_remove = set()
            for node in [self.volume_node, self.segmentation_node, self.pointListNode,
                        self.segmentEditorWidget.segmentationNode()] + self.loaded_markup_nodes + self.loaded_model_nodes:
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
            self.annulus_contour_node = None
            self.contour_nodes_by_label = {}
            self.centerline_nodes_by_label = {}
            self.centerline_points_world = {}
            self.centerline_arclength = {}
            
            self.current_index += 1
            self._resetReviewUI()
            self.load_json_case()
            self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))
        else:
            if self.volume_node:
                self.store_current_window_level_settings()
                slicer.mrmlScene.RemoveNode(self.volume_node)
            if self.segmentation_node:
                self.store_segment_visiblity_states()
                slicer.mrmlScene.RemoveNode(self.segmentation_node)
                if self.pointListNode:
                    slicer.mrmlScene.RemoveNode(self.pointListNode)
            
            self.current_index += 1
            self._resetReviewUI()
            self.load_nifti_file()
            self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))

    def _build_csv_row_and_save(self, file_path_display, mask_path_display):
        row_data = {
            'file': file_path_display,
            'comment': self.ui.comment.toPlainText(),
            'mask_path': mask_path_display,
            'mask_status': self._numerical_status_to_str(self.seg_mask_status[self.current_index])
        }
        
        seg_ratings = self._getSegRatings()
        for label in SEGMENTATION_LABELS:
            row_data[label] = self._rating_to_str(seg_ratings.get(label, RATING_NONE))
            
        meas_ratings = self._getMeasRatings()
        for meas in ALL_MEASUREMENT_COLUMNS:
            row_data[meas] = self._rating_to_str(meas_ratings.get(meas, RATING_NONE))
            
        csv_columns = ['file', 'comment', 'mask_path', 'mask_status'] + SEGMENTATION_LABELS + ALL_MEASUREMENT_COLUMNS
        df = pd.DataFrame([row_data], columns=csv_columns)
        
        csv_path = self.joinpath(self.directory, "annotations.csv")
        write_header = not os.path.exists(csv_path)
        df.to_csv(csv_path, mode='a', index=False, header=write_header)

    def save_and_next_clicked(self):
        if self.json_mode:
            self.save_and_next_json_clicked()
            return
        if self.n_files == 0 or self.current_index >= self.n_files:
            slicer.util.warningDisplay("No case is currently loaded.")
            return

        overall = self._getOverallRating()
        if overall == RATING_NONE:
            slicer.util.warningDisplay("Please select an overall rating before saving.")
            return

        self._saveCurrentReview()

        if not self.finish_flag and self.current_index < len(self.nifti_files):
            head, tail = os.path.split(self.nifti_files[self.current_index])
            file_display = self.nifti_files[self.current_index].replace(head, "").replace("/", "").replace("\\", "")
            mask_display = self.segmentation_files[self.current_index].replace(head, "").replace("/", "").replace("\\", "")
            
            self._build_csv_row_and_save(file_display, mask_display)
            self._saveDetailedReviewJson()
            
            self.reviewed_count += 1
            self.pending_count -= 1
            self._updateSummary()

        ret = 0
        if self.current_index <= self.n_files:
            if self.volume_node:
                self.store_current_window_level_settings()
                slicer.mrmlScene.RemoveNode(self.volume_node)
            if self.segmentation_node:
                self.store_segment_visiblity_states()
                slicer.mrmlScene.RemoveNode(self.segmentation_node)
                if self.pointListNode:
                    slicer.mrmlScene.RemoveNode(self.pointListNode)
            if self.unique_case_flag:
                while ret == 0 and self.current_index <= self.n_files:
                    self.current_index += 1
                    ret = self.load_nifti_file(unique=True)
                    if self.current_index == self.n_files:
                        self.finish_flag = True
                        break
            else:
                self.current_index += 1
                self.load_nifti_file()
            self._resetReviewUI()
            self._restoreReview(self.current_index)
            self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))
        else:
            self.finish_flag = True

    def save_and_next_json_clicked(self):
        if self.n_files == 0 or self.current_index >= self.n_files:
            slicer.util.warningDisplay("No case is currently loaded.")
            return

        overall = self._getOverallRating()
        if overall == RATING_NONE:
            slicer.util.warningDisplay("Please select an overall rating before saving.")
            return

        self._saveCurrentReview()

        if not self.finish_flag and self.current_index < self.n_files:
            file_display = self.nifti_files[self.current_index]
            mask_display = self.segmentation_files[self.current_index]
            
            self._build_csv_row_and_save(file_display, mask_display)
            self._saveDetailedReviewJson()
            
            self.reviewed_count += 1
            self.pending_count -= 1
            self._updateSummary()

        self.current_index += 1
        self._resetReviewUI()

        if self.current_index >= self.n_files:
            self.finish_flag = True
            self.ui.status_checked.setText("Checked: " + str(self.n_files) + " / " + str(self.n_files))
            slicer.util.infoDisplay("All cases have been reviewed.", "Finished")
            nodes_to_remove = set()
            for node in [self.volume_node, self.segmentation_node, self.pointListNode,
                         self.segmentEditorWidget.segmentationNode()] + self.loaded_markup_nodes + self.loaded_model_nodes:
                if node:
                    nodes_to_remove.add(node)
            for node in nodes_to_remove:
                slicer.mrmlScene.RemoveNode(node)
            self.loaded_markup_nodes = []
            self.loaded_model_nodes = []
            self.contour_nodes_by_label = {}
            self.centerline_nodes_by_label = {}
            self.centerline_points_world = {}
            self.centerline_arclength = {}
            self._refreshCenterlineTargets()
            return

        self.load_json_case()
        self._restoreReview(self.current_index)

    def _saveDetailedReviewJson(self):
        if not self.directory:
            return
        review_path = os.path.join(self.directory, "detailed_reviews.json")
        all_reviews = {}
        if os.path.exists(review_path):
            try:
                with open(review_path, 'r') as f:
                    all_reviews = json.load(f)
            except Exception:
                all_reviews = {}
        case_key = str(self.current_index)
        if self.current_index < len(self.case_ids):
            case_key = str(self.case_ids[self.current_index])
        all_reviews[case_key] = self.case_reviews.get(self.current_index, {})
        try:
            with open(review_path, 'w') as f:
                json.dump(all_reviews, f, indent=2)
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not save detailed review JSON: {e}")

    def onInputModeDirectoryToggled(self, checked):
        if not checked:
            return
        self.directoryInputWidget.setVisible(True)
        self.jsonInputWidget.setVisible(False)

    def onInputModeJsonToggled(self, checked):
        if not checked:
            return
        self.directoryInputWidget.setVisible(False)
        self.jsonInputWidget.setVisible(True)

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
                "Load a JSON case that contains this contour, or choose another target."
            )
            return
        self.align_views_to_contour(contour_node, target)

    # ------------------------------------------------------------------
    # Centerline slicing (slider-driven CPR-style axial alignment)
    # ------------------------------------------------------------------
    def _createCenterlineSlicingWidget_(self):
        """Build the 'Centerline Slicing' panel: a target combo box, an
        enable checkbox, and a slider that moves a cutting plane along the
        centerline while keeping that plane perpendicular to the local
        centerline tangent (i.e. a true cross-section of the vessel), the
        same way vessel/CPR analysis tools reformat along a path.
        """
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
        """Local tangent direction at points[index], via a central
        difference against its neighbours so the plane stays smoothly
        perpendicular to the centerline as the slider moves."""
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
        """Extract a dense, ordered array of world-space points from a
        centerline curve/markup node and the cumulative arc length along
        it, caching both under `label` for slider use."""
        points = self._get_markup_points_world(node)
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
        """Rebuild the centerline combo box / slider range for whatever
        centerline markups are loaded for the current case (called after
        each case load, and cleared out for directory-mode / no-data
        cases)."""
        if not hasattr(self, "centerlineTargetComboBox"):
            return

        self.centerlineTargetComboBox.blockSignals(True)
        self.centerlineTargetComboBox.clear()

        labels = sorted(self.centerline_nodes_by_label.keys()) if hasattr(self, "centerline_nodes_by_label") else []
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
            self.centerline_nodes_by_label.setdefault(label, None)
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
        # Leaving it unchecked simply stops the slider from driving the
        # Red view further; it does not revert prior slices.

    def onCenterlineSliceSizeChanged(self, _value=None):
        if self.centerlineEnableCheckBox.isChecked():
            self._applyCenterlineSlicePosition(self.centerlineSlider.value)

    def onCenterlineSliderChanged(self, value):
        self._updateCenterlinePositionLabel(value)
        if not self.centerlineEnableCheckBox.isChecked():
            return
        self._applyCenterlineSlicePosition(value)

    def _applyCenterlineSlicePosition(self, index):
        """Move all three slice planes to centerline point `index`, all
        pinned to the same point and built from the same tangent-aligned
        frame, so the crosshair stays centered on the centerline and every
        view stays perpendicular/tangential to it as the slider moves.
        This mirrors align_views_to_contour's Red/Yellow/Green axis
        assignment, just re-applied at each slider step instead of once
        for a static contour plane."""
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

        # Red: cross-section perpendicular to the centerline tangent (same
        # axis assignment as before).
        if red_view:
            self._set_slice_view_plane(red_view, x_axis, y_axis, z_axis, point, shared_fov)
        else:
            print("[Centerline] No Red-equivalent slice view found.")

        # Yellow / Green: longitudinal views that contain the tangent
        # direction, so they slide *along* the centerline instead of
        # staying frozen in the default sagittal/coronal orientation -
        # exactly the axis pattern align_views_to_contour uses for a
        # static contour plane, just re-applied every slider step.
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

    def onJsonManifestChanged(self, json_path):
        if hasattr(self, "inputModeJson") and not self.inputModeJson.isChecked():
            return
        if not json_path or not os.path.exists(json_path):
            return
        logger = logging.getLogger('TavrWorkbench')
        logger.setLevel(logging.DEBUG)
        try:
            with open(json_path, 'r') as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"[TavrWorkbench] ERROR: could not parse JSON manifest {json_path}: {e}")
            slicer.util.errorDisplay(f"Could not parse JSON manifest:\n{e}")
            return

        self.json_mode = True
        self.json_manifest_dir = os.path.dirname(json_path)
        self.directory = self.json_manifest_dir
        self.nifti_files = []
        self.segmentation_files = []
        self.seg_mask_status = []
        self.markup_paths_per_case = []
        self.centerline_model_paths_per_case = []
        self.case_ids = []
        self.current_index = 0
        self.finish_flag = False
        self.loaded_markup_nodes = []
        self.loaded_model_nodes = []
        self.annulus_contour_node = None
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self.centerline_points_world = {}
        self.centerline_arclength = {}
        self.case_reviews = {}

        fileHandler = logging.FileHandler(os.path.join(self.json_manifest_dir, 'tavr_workbench.log'))
        fileHandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(fileHandler)

        markup_group_keys = ["hinge_points", "contours", "max_diameters", "min_diameters", "heights", "centerline"]
        # Sub-keys within a group that are 3D model geometry (.vtp) rather than
        # point-based markups. These are loaded as models and are intentionally
        # excluded from the Measurement Review table.
        model_extensions = ('.vtp',)
        all_meas_keys = set()

        self.total_samples_in_dataset = len(manifest.get("samples", []))

        for sample in manifest.get("samples", []):
            image_path = sample.get("image", "")
            label_path = sample.get("label", "")
            case_id = sample.get("case_id", "")
            if not (isinstance(image_path, str) and os.path.exists(image_path) and self._is_valid_extension(image_path)):
                logger.info(f'Case {case_id}: image {image_path} missing or unsupported extension, skipping')
                continue
            self.nifti_files.append(image_path)
            self.case_ids.append(case_id)
            if isinstance(label_path, str) and os.path.exists(label_path) and self._is_valid_extension(label_path):
                self.segmentation_files.append(label_path)
                self.seg_mask_status.append(2)
            else:
                self.segmentation_files.append("")
                self.seg_mask_status.append(0)
                logger.info(f'Case {case_id}: no usable segmentation label found')

            case_markups = {}
            case_models = {}
            for group_key in markup_group_keys:
                group = sample.get(group_key)
                if not isinstance(group, dict):
                    continue
                for name, path in group.items():
                    full_key = f"{group_key}.{name}"
                    if not isinstance(path, str):
                        continue
                    if path.endswith(model_extensions):
                        # e.g. centerline.surface / centerline.curve (.vtp models)
                        if os.path.exists(path):
                            case_models[full_key] = path
                        else:
                            logger.info(f'Case {case_id}: model {full_key} missing at {path}')
                    elif path.endswith(('.mrk.json', '.json')):
                        if os.path.exists(path):
                            case_markups[full_key] = path
                            all_meas_keys.add(full_key)
                        else:
                            logger.info(f'Case {case_id}: markup {full_key} missing at {path}')
            self.markup_paths_per_case.append(case_markups)
            self.centerline_model_paths_per_case.append(case_models)

        all_files_snapshot = list(self.nifti_files)
        self.n_files = len(self.nifti_files)
        print(f"[TavrWorkbench] Parsed manifest: {self.n_files} usable cases found "
              f"(out of {self.total_samples_in_dataset} listed).")
        if self.n_files == 0:
            msg = ("No usable cases found in this manifest. Every 'image' path failed the "
                   "os.path.exists()/extension check.")
            print(f"[TavrWorkbench] ERROR: {msg}")
            slicer.util.errorDisplay(msg)
            return

        if os.path.exists(self.joinpath(self.directory, "annotations.csv")):
            ann_csv = pd.read_csv(self.joinpath(self.directory, "annotations.csv"))
            self.reviewed_count = len(ann_csv)
            self.nifti_files, self.segmentation_files, self.seg_mask_status, _, _ = self._restore_index(
                ann_csv, self.nifti_files, self.segmentation_files, self.seg_mask_status)
            kept_set = set(self.nifti_files)
            filtered_ids, filtered_markups, filtered_models = [], [], []
            for path, cid, mk, mdl in zip(all_files_snapshot, self.case_ids, self.markup_paths_per_case, self.centerline_model_paths_per_case):
                if path in kept_set:
                    filtered_ids.append(cid)
                    filtered_markups.append(mk)
                    filtered_models.append(mdl)
            self.case_ids = filtered_ids
            self.markup_paths_per_case = filtered_markups
            self.centerline_model_paths_per_case = filtered_models
            self.n_files = len(self.nifti_files)
            
            self._loadReviewsFromCSV()
        else:
            self.reviewed_count = 0
        
        self.pending_count = self.total_samples_in_dataset - self.reviewed_count

        ordered_keys = [k for k in MEASUREMENT_KEY_TO_LABEL if k in all_meas_keys]
        for k in sorted(all_meas_keys):
            if k not in ordered_keys:
                ordered_keys.append(k)
        self._buildMeasurementReviewTable(ordered_keys)

        self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))
        self._updateSummary()
        logger.info(f'Loaded {self.n_files} cases from JSON manifest {json_path}')
        self.load_json_case()
        self._restoreReview(self.current_index)

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
                        print(f"[Alignment] {view_name}: orientation set using {methodName}()")
                        break
                    except Exception as e:
                        print(f"[Alignment] {view_name}: {methodName} failed: {e}")
            if not orientation_set:
                try:
                    sliceNode.SetOrientation("Reformat")
                    print(f"[Alignment] {view_name}: orientation set using SetOrientation('Reformat')")
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
                    print(f"[Alignment] {view_name}: set FOV to {required_fov[0]:.1f} x {required_fov[1]:.1f} mm")
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
        print(f"[Alignment] {view_name}: plane set.")
        return True

    def align_views_to_contour(self, curve_node, contour_label="contour"):
        if not curve_node:
            print("[Alignment] No contour node provided.")
            return
        node_name = curve_node.GetName() if hasattr(curve_node, "GetName") else "unknown"
        print(f"[Alignment] Aligning views using contour: {contour_label} ({node_name})")
        points = self._get_markup_points_world(curve_node)
        if points.size == 0 or points.shape[0] < 3:
            print("[Alignment] Not enough points extracted from contour.")
            slicer.util.warningDisplay(f"Not enough points were found in '{contour_label}' to define a plane.")
            return
        if not np.all(np.isfinite(points)):
            print("[Alignment] Contour points contain non-finite values.")
            slicer.util.warningDisplay(f"Contour points for '{contour_label}' contain invalid coordinates.")
            return
        centroid = np.mean(points, axis=0)
        centered = points - centroid
        if np.linalg.norm(centered) < 1e-6:
            print("[Alignment] Contour points are degenerate.")
            slicer.util.warningDisplay(f"Contour points for '{contour_label}' are degenerate.")
            return
        try:
            u, s, vh = np.linalg.svd(centered)
        except Exception as e:
            print(f"[Alignment] SVD failed: {e}")
            slicer.util.warningDisplay(f"Plane fitting failed for '{contour_label}': {e}")
            return
        normal = vh[2].astype(float)
        if np.linalg.norm(normal) < 1e-9:
            print("[Alignment] Could not compute contour plane normal.")
            slicer.util.warningDisplay(f"Could not compute a plane normal for '{contour_label}'.")
            return
        if normal[2] < 0:
            normal = -normal
        x_axis, y_axis, z_axis = self._orthogonal_axes_from_normal(normal)
        print(f"[Alignment] Contour centroid: {centroid}")
        print(f"[Alignment] Red X axis: {x_axis}")
        print(f"[Alignment] Red Y axis: {y_axis}")
        print(f"[Alignment] Red Z axis / contour plane normal: {z_axis}")
        layoutManager = slicer.app.layoutManager()
        if len(layoutManager.sliceViewNames()) < 3:
            try:
                four_up = getattr(slicer.vtkMRMLLayoutNode, "SlicerLayoutFourUp", None)
                if four_up is not None:
                    layoutManager.setLayout(four_up)
                    slicer.app.processEvents()
                    print("[Alignment] Layout switched to Four-Up to expose Red/Yellow/Green views.")
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
        else:
            print("[Alignment] No Red-equivalent slice view found.")
        if yellow_view:
            self._set_slice_view_plane(yellow_view, x_axis, z_axis, -y_axis, centroid, shared_fov)
        else:
            print("[Alignment] No Yellow-equivalent slice view found.")
        if green_view:
            self._set_slice_view_plane(green_view, y_axis, z_axis, x_axis, centroid, shared_fov)
        else:
            print("[Alignment] No Green-equivalent slice view found.")
        try:
            layoutManager.forceRender()
        except Exception:
            pass
        print(f"[Alignment] Finished synchronized Red/Yellow/Green alignment using {contour_label}.")

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
        print("[Alignment] Slice views reset to default Axial/Sagittal/Coronal orientations.")

    def load_json_case(self):
        nodes_to_remove = set()
        for node in [self.volume_node, self.segmentation_node, self.pointListNode,
                      self.segmentEditorWidget.segmentationNode()] + self.loaded_markup_nodes + self.loaded_model_nodes:
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
        self.annulus_contour_node = None
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self.centerline_points_world = {}
        self.centerline_arclength = {}

        if self.current_index >= self.n_files:
            self.finish_flag = True
            return

        case_label = self.case_ids[self.current_index] if self.current_index < len(self.case_ids) else self.current_index
        image_path = self.nifti_files[self.current_index]
        print(f"[TavrWorkbench] Loading case {case_label} ({self.current_index + 1}/{self.n_files}): {image_path}")
        slicer.app.layoutManager().setRenderPaused(True)
        try:
            try:
                self.volume_node = slicer.util.loadVolume(image_path)
            except Exception as e:
                print(f"[TavrWorkbench] ERROR loading volume {image_path}: {e}")
                slicer.util.errorDisplay(f"Could not load volume for case {case_label}:\n{image_path}\n\n{e}")
                self.volume_node = None
            if self.volume_node is None:
                self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))
                return
            slicer.util.setSliceViewerLayers(background=self.volume_node)
            self.restore_window_level_settings()
            label_path = self.segmentation_files[self.current_index]
            if label_path:
                self.segmentation_node = self._load_segmentation_flexible(label_path)
                if self.segmentation_node:
                    self.restore_segment_visiblity_states()
                    try:
                        self.set_segmentation_and_mask_for_segmentation_editor()
                    except Exception as e:
                        print(f"[TavrWorkbench] WARNING: could not initialize segment editor for {label_path}: {e}")
                else:
                    print(f"[TavrWorkbench] WARNING: segmentation could not be loaded for case {case_label}: {label_path}")
            for label, path in self.markup_paths_per_case[self.current_index].items():
                try:
                    markupNode = slicer.util.loadMarkups(path)
                    if markupNode:
                        markupNode.SetName(label)
                        if not markupNode.GetDisplayNode():
                            markupNode.CreateDefaultDisplayNodes()
                        markupNode.GetDisplayNode().SetVisibility(True)
                        displayNode = markupNode.GetDisplayNode()
                        if displayNode and hasattr(displayNode, "SetSliceIntersectionVisibility"):
                            try:
                                displayNode.SetSliceIntersectionVisibility(True)
                            except Exception:
                                pass
                        self.loaded_markup_nodes.append(markupNode)
                        lower_label = label.lower()
                        if lower_label in ["contours.annulus", "contours.sov", "contours.stj"]:
                            self.contour_nodes_by_label[lower_label] = markupNode
                        point_count = "unknown"
                        if hasattr(markupNode, "GetNumberOfControlPoints"):
                            point_count = markupNode.GetNumberOfControlPoints()
                        print(f"[TavrWorkbench] Loaded markup '{label}' with {point_count} points from {path}")
                    else:
                        print(f"[TavrWorkbench] WARNING: loadMarkups returned None for {label}: {path}")
                except Exception as e:
                    print(f"[TavrWorkbench] WARNING: could not load markup {label} from {path}: {e}")

            # ---- Centerline models (surface.vtp / centerline.vtp) ----
            # These are 3D model files, not point-based markups, so they are
            # loaded with slicer.util.loadModel rather than loadMarkups, and
            # they are never added to the Measurement Review table.
            for label, path in self.centerline_model_paths_per_case[self.current_index].items():
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
                                # Semi-transparent surface, easy to see through
                                displayNode.SetColor(0.9, 0.85, 0.2)
                                displayNode.SetOpacity(0.35)
                            elif lower_label.endswith("curve"):
                                # Solid, brightly colored centerline curve
                                displayNode.SetColor(1.0, 0.1, 0.1)
                                if hasattr(displayNode, "SetLineWidth"):
                                    displayNode.SetLineWidth(3)
                            if hasattr(displayNode, "SetSliceIntersectionVisibility"):
                                try:
                                    displayNode.SetSliceIntersectionVisibility(True)
                                except Exception:
                                    pass
                        self.loaded_model_nodes.append(modelNode)
                        print(f"[TavrWorkbench] Loaded model '{label}' from {path}")
                    else:
                        print(f"[TavrWorkbench] WARNING: loadModel returned None for {label}: {path}")
                except Exception as e:
                    print(f"[TavrWorkbench] WARNING: could not load model {label} from {path}: {e}")
        finally:
            slicer.app.layoutManager().setRenderPaused(False)
            slicer.app.processEvents()

        for node in self.loaded_markup_nodes:
            name = node.GetName().lower() if node.GetName() else ""
            if name in ["contours.annulus", "contours.sov", "contours.stj"] and name not in self.contour_nodes_by_label:
                self.contour_nodes_by_label[name] = node
            if name.startswith("centerline.") and name not in self.centerline_nodes_by_label:
                self.centerline_nodes_by_label[name] = node

        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            try:
                layoutManager.sliceWidget(sliceViewName).sliceLogic().FitSliceToAll()
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: FitSliceToAll failed for {sliceViewName}: {e}")
        print(f"[TavrWorkbench] Available alignment targets: {list(self.contour_nodes_by_label.keys())}")
        print(f"[TavrWorkbench] Available centerline targets: {list(self.centerline_nodes_by_label.keys())}")

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
        if hasattr(self, "_enableMarkupsWidgetOptions"):
            self._enableMarkupsWidgetOptions()

        # Refresh the centerline-slicing slider/combo for this case.
        if hasattr(self, "_refreshCenterlineTargets"):
            self._refreshCenterlineTargets()

        self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))

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

    def overwrite_mask_clicked(self):
        if not self.nifti_files or self.current_index >= len(self.nifti_files):
            slicer.util.warningDisplay("No case is currently loaded.")
            return
        if self.directory is None:
            slicer.util.warningDisplay("No output directory is set.")
            return
        
        self.segmentation_node = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')
        if not self.segmentation_node:
            slicer.util.warningDisplay("No segmentation node found to save.")
            return
        
        # 1. PRIMARY: Use the explicit 'case_id' from the JSON manifest
        case_id = None
        if hasattr(self, 'case_ids') and self.current_index < len(self.case_ids):
            case_id = str(self.case_ids[self.current_index]).strip()
            
        # 2. FALLBACK 1: Use 'id_subs' if available (e.g., directory mode with mapping_unique.csv)
        if not case_id and hasattr(self, 'id_subs') and self.current_index < len(self.id_subs):
            case_id = str(self.id_subs[self.current_index]).strip()
            
        # 3. FALLBACK 2: Derive from the base filename without extensions
        if not case_id:
            filename = os.path.basename(self.nifti_files[self.current_index])
            case_id = filename
            for ext in ['.nii.gz', '.nii', '.nrrd']:
                if case_id.lower().endswith(ext):
                    case_id = case_id[:-len(ext)]
                    break
            else:
                case_id = os.path.splitext(case_id)[0]
        
        # Sanitize the case_id to ensure it's a valid, safe filename
        case_id = "".join(x for x in case_id if x.isalnum() or x in ('_', '-', '.')).strip()
        if not case_id:
            case_id = "unknown_case"

        # Construct the new .seg.nrrd file path using the case_id
        file_path_nrrd = self.joinpath(self.directory, f"{case_id}.seg.nrrd")
        
        # Update status and path tracking
        self.seg_mask_status[self.current_index] = 3
        self.segmentation_files[self.current_index] = file_path_nrrd
        
        # Save the segmentation node directly as .seg.nrrd
        slicer.util.saveNode(self.segmentation_node, file_path_nrrd)
        
        # Provide visual confirmation to the user
        slicer.util.infoDisplay(f"Segmentation saved successfully as:\n{file_path_nrrd}")

    def joinpath(self, rootdir, targetdir):
        return os.path.join(os.sep, rootdir + os.sep, targetdir)

    def _is_valid_extension(self, path):
        return any(path.endswith(i) for i in [".nii", ".nii.gz", ".nrrd"])

    def _construct_full_path(self, path):
        if not isinstance(path, str):
            return ""
        if os.path.isabs(path):
            return path
        else:
            return self.joinpath(self.directory, path)

    def _restore_index(self, ann_csv, files_list, mask_list, mask_status_list=None):
        statuses, unchecked_files, unchecked_masks, checked_ids, id_subs_list = [], [], [], [], []
        list_of_checked = ann_csv['file'].values
        list_of_checked = [self._construct_full_path(i) for i in list_of_checked]
        list_of_checked_masks = ann_csv['mask_path'].values
        list_of_checked_masks = [self._construct_full_path(i) for i in list_of_checked_masks]
        if self.unique_case_flag:
            checked_ids = []
            list_of_checked = ann_csv['file'].values
            for id_subj, img, _ in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if img in list_of_checked:
                    checked_ids.append(id_subj)
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if id_subj not in checked_ids:
                    id_subs_list.append(id_subj)
                    unchecked_files.append(self._construct_full_path(img))
                    if type(mask) == str:
                        unchecked_masks.append(self._construct_full_path(mask))
                        statuses.append(2)
                    else:
                        unchecked_masks.append("")
                        statuses.append(0)
        else:
            for i in range(len(files_list)):
                if files_list[i] not in list_of_checked:
                    unchecked_files.append(files_list[i])
                    unchecked_masks.append(mask_list[i])
                    statuses.append(mask_status_list[i])
        return unchecked_files, unchecked_masks, statuses, id_subs_list, checked_ids

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

    def onAtlasDirectoryChanged(self, directory):
        if hasattr(self, "inputModeDirectory") and not self.inputModeDirectory.isChecked():
            return
        self.json_mode = False
        self.nifti_files = []
        self.segmentation_files = []
        self.seg_mask_status = []
        self.id_subs = []
        self.id_subs_checked = []
        self.with_mapper_flag = False
        self.finish_flag = False
        self.current_index = 0
        self.annulus_contour_node = None
        self.contour_nodes_by_label = {}
        self.centerline_nodes_by_label = {}
        self.centerline_points_world = {}
        self.centerline_arclength = {}
        self.case_reviews = {}
        self.directory = os.path.normpath(directory)
        directory = self.directory
        logger = logging.getLogger('TavrWorkbench')
        logger.setLevel(logging.DEBUG)
        fileHandler = logging.FileHandler(self.joinpath(directory, 'tavr_workbench.log'))
        fileHandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(fileHandler)
        try:
            slicer.mrmlScene.RemoveNode(self.volume_node)
            slicer.mrmlScene.RemoveNode(self.segmentation_node)
        except:
            pass
        self.unique_case_flag = False
        if os.path.exists(self.joinpath(directory, "mapping_unique.csv")):
            id_subs = []
            self.mappings = pd.read_csv(self.joinpath(directory, "mapping_unique.csv"))
            self.unique_case_flag = True
            for id_subj, img, mask in zip(self.mappings["subj_id"], self.mappings["img_path"], self.mappings["mask_path"]):
                if os.path.exists(self.joinpath(directory, img)) and self._is_valid_extension(self.joinpath(directory, img)):
                    self.nifti_files.append(self.joinpath(directory, img))
                    id_subs.append(id_subj)
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory, mask)) and self._is_valid_extension(self.joinpath(directory, mask)):
                            self.segmentation_files.append(self.joinpath(directory, mask))
                            self.seg_mask_status.append(2)
                        elif self._is_valid_extension(self.joinpath(directory, mask)) and not os.path.exists(self.joinpath(directory, mask)):
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1)
                        else:
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0)
                    else:
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
            self.id_subs = id_subs
        elif os.path.exists(self.joinpath(directory, "mapping.csv")):
            self.mappings = pd.read_csv(self.joinpath(directory, "mapping.csv"))
            self.with_mapper_flag = True
            for img, mask in zip(self.mappings["img_path"], self.mappings["mask_path"]):
                if os.path.exists(self.joinpath(directory, img)) and self._is_valid_extension(self.joinpath(directory, img)):
                    self.nifti_files.append(self.joinpath(directory, img))
                    if type(mask) == str:
                        if os.path.exists(self.joinpath(directory, mask)) and self._is_valid_extension(self.joinpath(directory, mask)):
                            self.segmentation_files.append(self.joinpath(directory, mask))
                            self.seg_mask_status.append(2)
                        elif self._is_valid_extension(self.joinpath(directory, mask)) and not os.path.exists(self.joinpath(directory, mask)):
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(1)
                        else:
                            self.segmentation_files.append("")
                            self.seg_mask_status.append(0)
                    else:
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
        else:
            volume_extensions = (".nii.gz", ".nii", ".nrrd")
            mask_suffixes = ("_mask.nii.gz", "_mask.nii", "_mask.nrrd")
            for file in os.listdir(directory):
                if self._is_valid_extension(file) and "_mask" not in file:
                    self.nifti_files.append(self.joinpath(directory, file))
                    base = file
                    for ext in volume_extensions:
                        if base.endswith(ext):
                            base = base[: -len(ext)]
                            break
                    mask_found = False
                    for suffix in mask_suffixes:
                        candidate = self.joinpath(directory, base + suffix)
                        if os.path.exists(candidate):
                            self.segmentation_files.append(candidate)
                            self.seg_mask_status.append(2)
                            mask_found = True
                            break
                    if not mask_found:
                        self.segmentation_files.append("")
                        self.seg_mask_status.append(0)
        self.current_index = 0
        
        self.total_samples_in_dataset = len(self.nifti_files)
        
        if os.path.exists(self.joinpath(directory, "annotations.csv")):
            ann_csv = pd.read_csv(self.joinpath(directory, "annotations.csv"))
            self.reviewed_count = len(ann_csv)
            if self.unique_case_flag:
                self.nifti_files, self.segmentation_files, self.seg_mask_status, self.id_subs, self.id_subs_checked = self._restore_index(
                    ann_csv, self.nifti_files, self.segmentation_files, self.seg_mask_status)
            else:
                self.nifti_files, self.segmentation_files, self.seg_mask_status, _, _ = self._restore_index(
                    ann_csv, self.nifti_files, self.segmentation_files, self.seg_mask_status)
            
            self._loadReviewsFromCSV()
        else:
            self.reviewed_count = 0
        
        self.pending_count = self.total_samples_in_dataset - self.reviewed_count
        
        self.n_files = len(self.nifti_files)
        self.ui.measReviewContainer.setVisible(False)
        self.ui.status_checked.setText("Checked: " + str(self.current_index + 1) + " / " + str(self.n_files))
        self._updateSummary()
        # Directory mode never has centerline data, so keep the centerline
        # slicing controls disabled and empty.
        if hasattr(self, "_refreshCenterlineTargets"):
            self._refreshCenterlineTargets()
        self.load_nifti_file(self.unique_case_flag)
        self._restoreReview(self.current_index)

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
        if not self.segmentation_node:
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

    def load_nifti_file(self, unique=False):
        nodes_to_remove = set()
        for node in [self.volume_node, self.segmentation_node, self.pointListNode, self.segmentEditorWidget.segmentationNode()]:
            if node:
                nodes_to_remove.add(node)
        for node in nodes_to_remove:
            slicer.mrmlScene.RemoveNode(node)
        self.volume_node = None
        self.segmentation_node = None
        self.pointListNode = None
        self.annulus_contour_node = None
        self.contour_nodes_by_label = {}
        slicer.util.resetSliceViews()
        if unique:
            if self.current_index < self.n_files and self.id_subs[self.current_index] in self.id_subs_checked:
                return 0
            elif self.current_index == self.n_files:
                return 1
        slicer.app.layoutManager().setRenderPaused(True)
        try:
            self.volume_node = slicer.util.loadVolume(self.nifti_files[self.current_index])
            if self.volume_node:
                slicer.util.setSliceViewerLayers(background=self.volume_node)
            self.restore_window_level_settings()
            try:
                if self.segmentation_files[self.current_index]:
                    self.segmentation_node = slicer.util.loadSegmentation(self.segmentation_files[self.current_index])
                    if self.segmentation_node:
                        self.restore_segment_visiblity_states()
                        self.set_segmentation_and_mask_for_segmentation_editor()
            except Exception as e:
                print(f"Warning: could not load segmentation in load_nifti_file: {e}")
                if not unique:
                    self.enter()
        finally:
            slicer.app.layoutManager().setRenderPaused(False)
            slicer.app.processEvents()
        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            layoutManager.sliceWidget(sliceViewName).sliceLogic().FitSliceToAll()
        self._enableMarkupsWidgetOptions()
        return None

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
        self.pointListNode.SetName(f"Centroids_{self.case_ids[self.current_index] if self.current_index < len(self.case_ids) else self.current_index}")
        markupsLogic = slicer.modules.markups.logic()
        for segmentId in stats["SegmentIDs"]:
            if self.segment_visiblity_states.get(segmentId, True):
                centroid_ras = stats[segmentId, "LabelmapSegmentStatisticsPlugin.centroid_ras"]
                markupsLogic.JumpSlicesToLocation(*centroid_ras, False)

    def cleanup(self):
        self.removeObservers()

    def exit(self):
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        try:
            self.setParameterNode(None)
            self.segmentEditorWidget.setSegmentationNode(None)
            self.segmentEditorWidget.removeViewObservations()
        except:
            pass

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