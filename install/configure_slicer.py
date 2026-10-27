"""Register TavrWorkbench in a Slicer installation. Run by the installers inside Slicer's own Python:

    Slicer --no-splash --no-main-window --python-script configure_slicer.py

Environment variables (set by the installer):
    TAVR_MODULE_DIR   folder that contains TavrWorkbench.py
    TAVR_RESULT_FILE  the outcome is written here ("OK ..." or "ERROR ...") so the installer can check it
    TAVR_MODE         "configure" (default): write the settings, then read them back from disk
                      "verify": start Slicer normally and check that TavrWorkbench actually loaded

What "configure" changes:
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


def absolute(entry):
    return entry if os.path.isabs(entry) else os.path.join(slicer.app.slicerHome, entry)


def saved_on_disk(settings_file, key):
    """Read `key` straight from the .ini file (a fresh QSettings), not from Slicer's in-memory copy.
    Slicer does not report failed .ini writes; on macOS writing into an app in /Applications can
    fail silently, so the installer must check what actually reached the disk."""
    return as_list(qt.QSettings(settings_file, qt.QSettings.IniFormat).value(key))


def configure(module_dir):
    if not os.path.isfile(os.path.join(module_dir, MODULE_NAME + ".py")):
        raise RuntimeError(f"{MODULE_NAME}.py not found in {module_dir}")

    # Module path (stored per Slicer revision, exactly like Edit > Application Settings > Modules)
    rev = slicer.app.revisionUserSettings()
    rev_file = slicer.app.slicerRevisionUserSettingsFilePath
    kept, removed = [], []
    for entry in as_list(rev.value("Modules/AdditionalPaths")):
        path = absolute(entry)
        if norm(path) == norm(module_dir):
            continue  # re-added below, once
        other_copy = os.path.isfile(os.path.join(path, MODULE_NAME + ".py"))
        stale_copy = os.path.basename(os.path.normpath(path)) == MODULE_NAME and not os.path.isdir(path)
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

    # Check that both settings really reached the disk
    if not any(norm(absolute(p)) == norm(module_dir) for p in saved_on_disk(rev_file, "Modules/AdditionalPaths")):
        writable = os.access(rev_file if os.path.exists(rev_file) else os.path.dirname(rev_file), os.W_OK)
        raise RuntimeError(
            f"The module path could not be saved to {rev_file} "
            f"(settings status {rev.status()}, writable: {writable}). "
            "On macOS this happens when Slicer is in a protected folder such as /Applications.")
    if MODULE_NAME not in saved_on_disk(slicer.app.slicerUserSettingsFilePath, "Modules/FavoriteModules"):
        raise RuntimeError(f"The favorite module could not be saved to {slicer.app.slicerUserSettingsFilePath}")

    lines = [f"Slicer {slicer.app.applicationVersion} (revision {slicer.app.revision})",
             f"Module path: {module_dir}",
             f"Favorite modules: {', '.join(favorites)}",
             f"Settings: {rev_file}"]
    if removed:
        lines.append("Removed other TavrWorkbench module paths: " + "; ".join(removed))
    return "\n".join(lines)


def verify(module_dir):
    """Runs in a normal Slicer start: the module must have been found on the saved path and loaded."""
    module = slicer.app.moduleManager().module(MODULE_NAME)
    if module is None:
        paths = as_list(slicer.app.revisionUserSettings().value("Modules/AdditionalPaths"))
        raise RuntimeError(
            f"Slicer started but did not load {MODULE_NAME}.\n"
            f"Module paths Slicer read: {paths or 'none'}\n"
            "Any Python error printed above by Slicer shows why the module failed to load.")
    path = str(module.path)
    if norm(os.path.dirname(path)) != norm(module_dir):
        raise RuntimeError(f"Slicer loaded {MODULE_NAME} from a different copy: {path}")
    return f"TavrWorkbench loads in Slicer: {path}"


def write_result(text):
    path = os.environ.get("TAVR_RESULT_FILE")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


exit_code = 0
try:
    module_dir = os.environ["TAVR_MODULE_DIR"]
    step = verify if os.environ.get("TAVR_MODE") == "verify" else configure
    write_result("OK\n" + step(module_dir))
except Exception as e:
    exit_code = 1
    write_result("ERROR\n" + (str(e) if isinstance(e, RuntimeError) else traceback.format_exc()))


def _quit():
    try:
        slicer.util.exit(exit_code)
    except Exception:
        slicer.app.exit(exit_code)


# Quit once the event loop runs (quitting before it starts would be ignored)
qt.QTimer.singleShot(0, _quit)
