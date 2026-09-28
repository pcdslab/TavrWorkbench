# TavrWorkbench

<p align="center">
  <img src="TavrWorkbench.png" alt="TavrWorkbench Icon Dark", width=200>
</p>
TavrWorkbench is a 3D Slicer extension for fast and structured review of TAVR CT segmentations and measurements. It lets a reviewer step through a dataset case by case, inspect the CT volume together with its segmentation and anatomical markups, rate the quality of each result, correct the mask when needed, and export everything to a clean annotation file.

![TavrWorkbench main panel](/TavrWorkbench/Screenshots/main_panel.png)

## Use Case

Automated TAVR pipelines produce segmentations of the aorta, aortic root, left ventricle, coronaries and thoracic aorta, along with measurements such as annulus, sinus of Valsalva (SOV) and sinotubular junction (STJ) contours, diameters, hinge points, heights and centerlines. Before these outputs can be trusted for research or planning, an expert has to check them. TavrWorkbench turns that check into a quick and repeatable workflow, where each case receives an overall rating, a rating for every segmentation label and measurement, and an optional comment. Cases that need small fixes can be edited right inside the same module.

![Review workflow](/TavrWorkbench/Screenshots/review_workflow.png)


## Installation

1. Open 3D Slicer and go to the Extensions Manager.
2. Search for TavrWorkbench and click Install.
3. Restart 3D Slicer and open the module from the module selector.

The module installs pandas, numpy and SimpleITK automatically on first launch if they are missing.

## Inputs

The Input panel offers two ways to load a dataset. Choose one using the Directory or JSON Manifest option.

### Directory Mode

Select a folder that contains your volumes in .nii, .nii.gz or .nrrd format. The module finds the cases in one of three ways.

1. Automatic pairing: each volume is matched with a mask that shares its name and ends with _mask, for example case01.nii.gz and case01_mask.nii.gz.
2. mapping.csv: a file with the columns img_path and mask_path, where paths are relative to the folder or absolute.
3. mapping_unique.csv: the same as above with an extra subj_id column, so that only one image per subject is presented for review.

Cases without a mask are still loaded, and you can review them without a segmentation.

### JSON Manifest Mode (Recommended)

Select a manifest file that describes each sample. Every entry under samples can contain the following fields.

1. case_id, image and label, which give the case name, the CT volume and the segmentation.
2. hinge_points, contours, max_diameters, min_diameters and heights, which point to markup files in .mrk.json format.
3. centerline, which can point to a markup file for the centerline points and to .vtp model files for the centerline curve and surface.

A minimal example is shown below.

```json
{
  "samples": [
    {
      "case_id": "case01",
      "image": "/data/case01/image.nii.gz",
      "label": "/data/case01/label.nii.gz",
      "contours": { "annulus": "/data/case01/annulus.mrk.json" },
      "hinge_points": { "LCC": "/data/case01/lcc.mrk.json" }
    }
  ]
}
```

The Measurement Review table is built automatically from the markups found in your manifest.

![Input panel](/TavrWorkbench/Screenshots/input_panel.png)


## Reviewing Cases

1. Load a directory or a manifest. The first case opens automatically, and the counter at the top shows your position, for example Checked: 1 / 50.
2. Inspect the volume, the segmentation and the markups in the slice and 3D views.
3. Choose an overall rating of Acceptable, Minor correction or Not acceptable. This fills in every row of the review tables, and you can then change individual rows where they differ.
4. Add a comment if needed. The Clear button resets all ratings for the current case.
5. Click Save and Next, or press Shift+Return, to store the review and open the next case. An overall rating is required before saving.

To move around the dataset, use Previous to return to an earlier case, where your ratings are restored, and Skip to move forward without saving anything. The Summary section shows the total number of samples, how many are reviewed and how many are pending.

![Review panel](/TavrWorkbench/Screenshots/review_panel.png)

## Modifying Segmentations

The Segmentation Editor panel gives access to the standard Slicer editing tools such as Paint, Erase, Scissors, Smoothing and Islands. After correcting a mask, click Save Mask to write it as a .seg.nrrd file named after the case ID. The Markups panel is also available for adjusting points and contours.

## View Tools

View Alignment reorients the Red, Yellow and Green views to the plane of the annulus, SOV or STJ contour, or resets them to the default orientation. Centerline Slicing lets you move a slider along the centerline so that the views follow the vessel with a true cross section at every position.

![View tools](/TavrWorkbench/Screenshots/view_tools.png)
![View tools](/TavrWorkbench/Screenshots/view_tools_2.png)
## Outputs

All outputs are written to the input folder, or to the manifest folder in JSON mode.

| File | Contents |
|---|---|
| `annotations.csv` | One row per reviewed case, with all ratings and comments |
| `detailed_reviews.json` | Same review data, keyed by case ID |
| `tavr_workbench.log` | Run log for troubleshooting |
| `<case_id>.seg.nrrd` | Saved when you click **Save Mask** to overwrite a corrected segmentation |

When you reopen the same dataset, cases already listed in annotations.csv are skipped, so you can stop and resume a review session at any time.

## Acknowledgements

Developed by Mohammed Khubaib, M.S. Computer Engineering, Florida International University, as part of the Saeed Lab under the supervision of Dr. Fahad Saeed and Dr. Kaoutar Ben Ahmed.