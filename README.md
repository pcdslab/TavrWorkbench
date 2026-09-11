# TavrWorkbench

<p align="center">
  <img src="TavrWorkbench.png" alt="TavrWorkbench Icon Dark", width=200>
</p>

<!-- ![TavrWorkbench Icon](TavrWorkbench.png) -->

A 3D Slicer extension for reviewing TAVR (transcatheter aortic valve replacement) CT segmentations and measurements, rate quality case by case, leave comments, and track progress across a dataset.

## What it does

- Loads CT volumes with their segmentations (Aorta, Aortic Root, Left Ventricle, Coronaries, Thoracic Aorta) one case at a time.
- Lets you rate each case **overall**, per **segmentation label**, and per **measurement** (✓ Acceptable / △ Minor correction / ✕ Not acceptable), plus a free-text comment.
- Tracks review progress (Total / Reviewed / Pending) and saves everything to disk as you go, so you can stop and resume later.
- Aligns the 2D slice views to a loaded contour (annulus, SOV, STJ), or slides a cross-section along a centerline curve.
- Includes a built-in Segment Editor and Markups panel for correcting segmentations directly.

## Requirements

- 3D Slicer (with the **Segmentations** and **Markups** modules, and the **SegmentStatistics** module).
- Python packages `pandas`, `numpy`, `SimpleITK`, installed automatically on first run if missing.

## Installing

1. Open Slicer → **Developer Tools → Extension Wizard**.
2. Click **Select Extension** and point it at the `TavrWorkbench` folder.
3. The `TavrWorkbench` module will appear in the module dropdown.

## Input data

You can load a dataset in one of two ways:

**Directory mode** : pick a folder containing:
- `*.nii` / `*.nii.gz` / `*.nrrd` volumes, optionally paired with masks named `<volume>_mask.nii.gz`
- or a `mapping.csv` / `mapping_unique.csv` with `img_path`, `mask_path` (and `subj_id` for the "unique" variant)

### Recommended:
**JSON manifest mode** : pick a `.json` file shaped like this (top-level metadata is optional/informational; only `samples` is read):
```json
{
  "name": "Full Dataset for TAVR-related Structure Segmentation",
  "description": "101 CTA scans with Annotations for Aorta, Aortic Root and Left Ventricle annotations along with the measurements",
  "modality": "CT",
  "totaldatasample": 101,
  "samples": [
    {
      "case_id": "568",
      "image": "/Volumes/falcon/tavr_application/imgs/568.img.nii.gz",
      "label": "/Volumes/falcon/tavr_application/stj_labels_corrected_v1/568.seg.nrrd",
      "hinge_points": {
        "LCC": "/Volumes/falcon/tavr_application/hinge_points/v2/568/LCC.mrk.json",
        "RCC": "/Volumes/falcon/tavr_application/hinge_points/v2/568/RCC.mrk.json",
        "NCC": "/Volumes/falcon/tavr_application/hinge_points/v2/568/NCC.mrk.json"
      },
      "contours": {
        "annulus": "/Volumes/falcon/tavr_application/annulus_results_17/568/annulus_contour.mrk.json",
        "sov": "/Volumes/falcon/tavr_application/sov/568/sov_contour.mrk.json",
        "stj": "/Volumes/falcon/tavr_application/stj_contour/568/stj_contour.mrk.json"
      },
      "max_diameters": {
        "annulus": "/Volumes/falcon/tavr_application/annulus_results_17/568/annulus_max_d.mrk.json",
        "sov": "/Volumes/falcon/tavr_application/sov/568/sov_max_diameter_line.mrk.json",
        "stj": "/Volumes/falcon/tavr_application/stj_contour/568/stj_max_d.mrk.json"
      },
      "min_diameters": {
        "annulus": "/Volumes/falcon/tavr_application/annulus_results_17/568/annulus_min_d.mrk.json",
        "sov": "/Volumes/falcon/tavr_application/sov/568/sov_min_diameter_line.mrk.json",
        "stj": "/Volumes/falcon/tavr_application/stj_contour/568/stj_min_d.mrk.json"
      },
      "heights": {
        "stj": "/Volumes/falcon/tavr_application/stj_heights/568/STJ_H.mrk.json",
        "lch": "/Volumes/falcon/tavr_application/coronary_ostium_points/568/LCH.mrk.json",
        "rch": "/Volumes/falcon/tavr_application/coronary_ostium_points/568/RCH.mrk.json"
      }
    }
  ]
}
```

Per sample, `case_id`, `image`, and `label` are the essentials; `hinge_points`, `contours`, `max_diameters`, `min_diameters`, and `heights` each hold named `.mrk.json` markup files that get loaded and (aside from `hinge_points`) show up as rows in the Measurement Review table. A `centerline` group is also supported, for `.mrk.json` markup points plus optional `.vtp` model files (e.g. `centerline.surface`, `centerline.curve`) used by the Centerline Slicing panel. Any extra fields your data has, like `dirs` or `aortic_angle`, are simply ignored by the extension.

## Output files

Written into the same directory as your input:

| File | Contents |
|---|---|
| `annotations.csv` | One row per reviewed case, with all ratings and comments |
| `detailed_reviews.json` | Same review data, keyed by case ID |
| `tavr_workbench.log` | Run log for troubleshooting |
| `<case_id>.seg.nrrd` | Saved when you click **Save Mask** to overwrite a corrected segmentation |

## Contributors

Mohammed Khubaib (Saeed Lab, Florida International University), under the supervision of Dr. Fahad Saeed and Dr. Kaoutar Ben Ahmed.

## License