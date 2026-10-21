"""Embedded Segment Editor, mask loading and per-segment visibility memory."""
import logging

import qt
import slicer

EFFECT_ORDER = [
    "No editing", "Threshold",
    "Paint", "Draw",
    "Erase", "Level tracing",
    "Grow from seeds", "Fill between slices",
    "Margin", "Hollow",
    "Smoothing", "Scissors",
    "Islands", "Logical operators",
    "Mask volume",
]
SEGMENT_EDITOR_SINGLETON = "SegmentEditor"


class SegmentationController:
    def __init__(self, container):
        import qSlicerSegmentationsModuleWidgetsPythonQt

        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.widget = qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget()
        self.widget.setMaximumNumberOfUndoStates(10)
        self.parameter_node = None
        self.select_parameter_node()
        self.widget.setMRMLScene(slicer.mrmlScene)
        self.widget.unorderedEffectsVisible = False
        self.widget.setEffectNameOrder(EFFECT_ORDER)
        layout.addWidget(self.widget)

        self.node = None               # segmentation node of the current case
        self.visibility_states = {}    # segment id -> visible, kept across cases

    # ------------------------------------------------------------ editor
    def select_parameter_node(self):
        node = slicer.mrmlScene.GetSingletonNode(SEGMENT_EDITOR_SINGLETON, "vtkMRMLSegmentEditorNode")
        if node is None:
            node = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            node.UnRegister(None)
            node.SetSingletonTag(SEGMENT_EDITOR_SINGLETON)
            node = slicer.mrmlScene.AddNode(node)
        self.parameter_node = node
        self.widget.setMRMLSegmentEditorNode(node)

    def refresh(self):
        self.select_parameter_node()
        self.widget.updateWidgetFromMRML()

    def deactivate_effect(self):
        try:
            self.widget.setActiveEffect(None)
        except Exception:
            pass

    # ----------------------------------------------------------- loading
    @staticmethod
    def load(path):
        """Load a .seg.nrrd or a labelmap (.nii/.nii.gz/.nrrd) as a segmentation node."""
        try:
            node = slicer.util.loadSegmentation(path)
            if node:
                return node
        except Exception as e:
            print(f"[TavrWorkbench] loadSegmentation failed for {path}: {e}")
        try:
            labelmap = slicer.util.loadLabelVolume(path)
            if not labelmap:
                return None
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmap, node)
            slicer.mrmlScene.RemoveNode(labelmap)
            return node
        except Exception as e:
            print(f"[TavrWorkbench] Could not load segmentation from {path}: {e}")
            logging.getLogger("TavrWorkbench").info(f"Could not load segmentation from {path}: {e}")
            return None

    @staticmethod
    def create_empty(name, volume_node):
        """Empty segmentation so cases without a label can still be segmented and saved."""
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", name)
        node.CreateDefaultDisplayNodes()
        if volume_node is not None:
            node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        return node

    def attach(self, node, volume_node):
        self.node = node
        self.restore_visibility()
        slicer.app.processEvents()
        self.select_parameter_node()
        self.widget.setSegmentationNode(node)
        self.widget.setSourceVolumeNode(volume_node)

    def release(self):
        """Detach from the editor and return the nodes that belong to the current case."""
        nodes = [self.node]
        try:
            nodes.append(self.widget.segmentationNode())
        except Exception:
            pass
        try:
            self.widget.setSegmentationNode(None)
        except Exception:
            pass
        self.node = None
        return [n for n in nodes if n is not None]

    def on_scene_start_close(self):
        try:
            self.widget.setSegmentationNode(None)
            self.widget.removeViewObservations()
        except Exception:
            pass
        self.node = None

    # --------------------------------------------------------- display
    def set_display(self, outline_only, visible):
        d = self.node.GetDisplayNode() if self.node else None
        if not d:
            return
        d.SetVisibility(bool(visible))
        d.SetVisibility2DFill(not outline_only)
        d.SetVisibility2DOutline(True)

    def store_visibility(self):
        d = self.node.GetDisplayNode() if self.node else None
        if not d:
            return
        for sid in self.node.GetSegmentation().GetSegmentIDs():
            self.visibility_states[sid] = d.GetSegmentVisibility(sid)

    def restore_visibility(self):
        d = self.node.GetDisplayNode() if self.node else None
        if not d:
            return
        for sid in self.node.GetSegmentation().GetSegmentIDs():
            d.SetSegmentVisibility(sid, self.visibility_states.get(sid, True))

    def jump_to_centroids(self):
        """Move the slice views onto the visible segments (ends on the last visible one)."""
        if not self.node or self.node.GetSegmentation().GetNumberOfSegments() == 0:
            return
        try:
            import SegmentStatistics
            logic = SegmentStatistics.SegmentStatisticsLogic()
            pn = logic.getParameterNode()
            pn.SetParameter("Segmentation", self.node.GetID())
            pn.SetParameter("LabelmapSegmentStatisticsPlugin.centroid_ras.enabled", str(True))
            logic.computeStatistics()
            stats = logic.getStatistics()
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not compute segment centroids: {e}")
            return
        markups_logic = slicer.modules.markups.logic()
        for sid in stats["SegmentIDs"]:
            key = (sid, "LabelmapSegmentStatisticsPlugin.centroid_ras")
            if self.visibility_states.get(sid, True) and key in stats:
                markups_logic.JumpSlicesToLocation(*stats[key], False)
