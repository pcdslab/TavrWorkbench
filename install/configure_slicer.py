"""Register TavrWorkbench in a Slicer installation. Run by the installers inside Slicer's own Python:

    Slicer --no-splash --no-main-window --python-script configure_slicer.py

Environment variables (set by the installer):
    TAVR_MODULE_DIR   folder that contains TavrWorkbench.py
    TAVR_RESULT_FILE  the outcome is written here ("OK ..." or "ERROR ...") so the installer can check it

What it changes:
    * revision settings  Modules/AdditionalPaths  += TAVR_MODULE_DIR  (other copies of the module are removed)
    * user settings      Modules/FavoriteModules  += TavrWorkbench
"""
import os
import traceback

import qt
import slicer

MODULE_NAME = "TavrWorkbench"


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def register(module_dir):
    if not os.path.isfile(os.path.join(module_dir, MODULE_NAME + ".py")):
        raise RuntimeError(f"{MODULE_NAME}.py not found in {module_dir}")

    # Module path (stored per Slicer revision, exactly like Edit > Application Settings > Modules)
    rev = slicer.app.revisionUserSettings()
    kept, removed = [], []
    for entry in as_list(rev.value("Modules/AdditionalPaths")):
        absolute = entry if os.path.isabs(entry) else os.path.join(slicer.app.slicerHome, entry)
        if norm(absolute) == norm(module_dir):
            continue  # re-added below, once
        other_copy = os.path.isfile(os.path.join(absolute, MODULE_NAME + ".py"))
        stale_copy = os.path.basename(os.path.normpath(absolute)) == MODULE_NAME and not os.path.isdir(absolute)
        if other_copy or stale_copy:
            removed.append(entry)  # two copies of the same module would conflict
            continue
        kept.append(entry)
    kept.append(module_dir)
    rev.setValue("Modules/AdditionalPaths", kept)
    rev.sync()

    # Favorite modules toolbar
    user = slicer.app.userSettings()
    favorites = as_list(user.value("Modules/FavoriteModules"))
    if MODULE_NAME not in favorites:
        favorites.append(MODULE_NAME)
    user.setValue("Modules/FavoriteModules", favorites)
    user.sync()

    lines = [f"Slicer {slicer.app.applicationVersion} (revision {slicer.app.revision})",
             f"Module path: {module_dir}",
             f"Favorite modules: {', '.join(favorites)}",
             f"Settings: {slicer.app.slicerRevisionUserSettingsFilePath}"]
    if removed:
        lines.append("Removed other TavrWorkbench module paths: " + "; ".join(removed))
    return "\n".join(lines)


def write_result(text):
    path = os.environ.get("TAVR_RESULT_FILE")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


exit_code = 0
try:
    write_result("OK\n" + register(os.environ["TAVR_MODULE_DIR"]))
except Exception:
    exit_code = 1
    write_result("ERROR\n" + traceback.format_exc())


def _quit():
    try:
        slicer.util.exit(exit_code)
    except Exception:
        slicer.app.exit(exit_code)


# Quit once the event loop runs (quitting before it starts would be ignored)
qt.QTimer.singleShot(0, _quit)
