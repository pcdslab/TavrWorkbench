cmake_minimum_required(VERSION 3.28.0...3.28.0 FATAL_ERROR)

project(TavrWorkbench)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/pcdslab/TavrWorkbench")
set(EXTENSION_CONTRIBUTORS "Mohammed Khubaib (Florida International University (Saeed Lab)), Dr. Fahad Saeed (Florida International University (Saeed Lab)), Dr. Kaoutar (Florida International University (Saeed Lab))")
set(EXTENSION_DESCRIPTION "A 3D Slicer extension for fast, structured review of TAVR CT segmentations and measurements.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/TavrWorkbench.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/TavrWorkbench.png")
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