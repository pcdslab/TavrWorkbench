cmake_minimum_required(VERSION 3.16.3...3.22.6 FATAL_ERROR)

project(TavrWorkbench)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/pcdslab/TavrWorkbench")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Mohammed Khubaib (Florida International University), Fahad Saeed (Florida International University), Kaoutar Ben Ahmed (Florida International University)")
set(EXTENSION_DESCRIPTION "A 3D Slicer extension for fast, structured review of TAVR CT segmentations and measurements. Reviewers step through cases, rate each segmentation label and measurement, correct masks, and export the results to CSV.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/TavrWorkbench/Resources/Icons/TavrWorkbench.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/Screenshots/main_panel.png https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/Screenshots/review_panel.png https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/Screenshots/view_tools.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(TavrWorkbench)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})