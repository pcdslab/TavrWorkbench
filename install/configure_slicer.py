"""Register TavrWorkbench in a Slicer installation. Run by the installers inside Slicer's own Python:

    Slicer --no-splash --no-main-window --python-script configure_slicer.py

Environment variables (set by the installer):
    TAVR_MODULE_DIR   folder that contains TavrWorkbench.py
    TAVR_RESULT_FILE  the outcome is written here ("OK ..." or "ERROR ...") so the installer can check it
    TAVR_MODE         "configure" (default): register the module
                      "verify": check that TavrWorkbench loads in this Slicer

How the module is registered (two independent ways, so one failing is harmless):
    1. Slicer's startup file in the user's home folder (~/.slicerrc.py, or $SLICERRC): a small marked
       block loads TavrWorkbench at every start. This file is always writable, unlike the settings
       file inside Slicer.app, which macOS can silently refuse to change.
    2. revision settings  Modules/AdditionalPaths += TAVR_MODULE_DIR  (Edit > Application Settings >
       Modules); used when Slicer can save it.
Plus user settings Modules/FavoriteModules += TavrWorkbench (the Favorite modules toolbar).
"""
import os
import sys
import traceback

import qt
import slicer

MODULE_NAME = "TavrWorkbench"
BLOCK_BEGIN = "# >>> TavrWorkbench >>> (added by the TavrWorkbench installer; remove this block to unload it)"
BLOCK_END = "# <<< TavrWorkbench <<<"


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
    """Read `key` straight from the .ini file (a fresh QSettings), not from Slicer's in-memory copy."""
    return as_list(qt.QSettings(settings_file, qt.QSettings.IniFormat).value(key))


# ------------------------------------------------------------------ startup file (~/.slicerrc.py)
def rc_file():
    return os.environ.get("SLICERRC") or os.path.join(os.path.expanduser("~"), ".slicerrc.py")


def rc_block(module_dir):
    return f"""{BLOCK_BEGIN}
def _tavrworkbench_load(module_dir={module_dir!r}):
    import os, qt, slicer
    module_file = os.path.join(module_dir, "{MODULE_NAME}.py")
    if slicer.app.moduleManager().module("{MODULE_NAME}") is not None or not os.path.isfile(module_file):
        return  # already loaded (e.g. from the module paths setting) or uninstalled
    factory = slicer.app.moduleManager().factoryManager()
    factory.registerModule(qt.QFileInfo(module_file))
    if not factory.loadModules(["{MODULE_NAME}"]):
        print("TavrWorkbench could not be loaded from " + module_dir)
try:
    _tavrworkbench_load()
except Exception as _tavr_error:
    print("TavrWorkbench could not be loaded:", _tavr_error)
{BLOCK_END}
"""


def strip_block(text):
    """Remove an earlier TavrWorkbench block (so re-running the installer never duplicates it)."""
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith(BLOCK_BEGIN.split(" (")[0]):
            skipping = True
            continue
        if skipping and line.startswith(BLOCK_END):
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "".join(out)


def write_rc(module_dir):
    path = rc_file()
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    text = strip_block(old).rstrip("\n")
    text = (text + "\n\n" if text else "") + rc_block(module_dir)
    tmp = path + ".tavr-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    with open(path, encoding="utf-8") as f:
        if rc_block(module_dir) not in f.read():
            raise RuntimeError(f"Could not write Slicer's startup file {path}")
    return path


def read_rc_block():
    path = rc_file()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.find(BLOCK_BEGIN.split(" (")[0])
    end = text.find(BLOCK_END, start)
    return text[start:end] if start >= 0 and end > start else None


# ------------------------------------------------------------------ steps
def configure(module_dir):
    if not os.path.isfile(os.path.join(module_dir, MODULE_NAME + ".py")):
        raise RuntimeError(f"{MODULE_NAME}.py not found in {module_dir}")
    notes = []

    # 1. Startup file in the home folder (the reliable way)
    rc_path = write_rc(module_dir)
    app_rc = os.path.join(slicer.app.slicerHome, ".slicerrc.py")
    if os.path.exists(app_rc):
        notes.append(f"Note: {app_rc} exists and is used instead of {rc_path}; "
                     "the module paths setting below must work.")

    # 2. Module paths setting (inside Slicer's install folder; may be refused on macOS)
    rev = slicer.app.revisionUserSettings()
    rev_file = slicer.app.slicerRevisionUserSettingsFilePath
    kept, removed = [], []
    for entry in as_list(rev.value("Modules/AdditionalPaths")):
        path = absolute(entry)
        if norm(path) == norm(module_dir):
            continue
        other_copy = os.path.isfile(os.path.join(path, MODULE_NAME + ".py"))
        stale_copy = os.path.basename(os.path.normpath(path)) == MODULE_NAME and not os.path.isdir(path)
        if other_copy or stale_copy:
            removed.append(entry)  # two copies of the same module would conflict
            continue
        kept.append(entry)
    kept.append(module_dir)
    rev.setValue("Modules/AdditionalPaths", kept)
    rev.sync()
    path_saved = any(norm(absolute(p)) == norm(module_dir)
                     for p in saved_on_disk(rev_file, "Modules/AdditionalPaths"))

    # Favorite modules toolbar (user settings in the home folder)
    user = slicer.app.userSettings()
    favorites = as_list(user.value("Modules/FavoriteModules"))
    if MODULE_NAME not in favorites:
        favorites.append(MODULE_NAME)
    user.setValue("Modules/FavoriteModules", favorites)
    user.sync()
    if MODULE_NAME not in saved_on_disk(slicer.app.slicerUserSettingsFilePath, "Modules/FavoriteModules"):
        notes.append("Note: the Favorite modules toolbar could not be updated; "
                     "TavrWorkbench is still under Modules > Examples.")

    lines = [f"Slicer {slicer.app.applicationVersion} (revision {slicer.app.revision})",
             f"Module folder: {module_dir}",
             f"Startup file: {rc_path}",
             "Module paths setting: " + ("saved" if path_saved else
                                         "not saved by Slicer (fine: the startup file loads the module)"),
             f"Favorite modules: {', '.join(favorites)}"]
    if removed:
        lines.append("Removed other TavrWorkbench module paths: " + "; ".join(removed))
    return "\n".join(lines + notes)


def verify(module_dir):
    """The module must load in this Slicer: on its own (module paths setting / startup file), or
    by running the installer's startup-file block, exactly as a normal Slicer start would."""
    manager = slicer.app.moduleManager()
    how = "module paths setting"
    if manager.module(MODULE_NAME) is None:
        block = read_rc_block()
        if block is None:
            raise RuntimeError(f"The TavrWorkbench block is missing from {rc_file()}")
        exec(compile(block, rc_file(), "exec"), {"__name__": "__slicerrc__"})
        how = "startup file"
    module = manager.module(MODULE_NAME)
    if module is None:
        # Import the module directly to show the actual Python error
        sys.path.insert(0, module_dir)
        try:
            __import__(MODULE_NAME)
        except Exception:
            raise RuntimeError(f"{MODULE_NAME} failed to load because of this error:\n{traceback.format_exc()}")
        raise RuntimeError(f"Slicer did not load {MODULE_NAME} from {module_dir} (no Python error was reported).")
    path = str(module.path)
    if norm(os.path.dirname(path)) != norm(module_dir):
        raise RuntimeError(f"Slicer loaded {MODULE_NAME} from a different copy: {path}")
    return f"TavrWorkbench loads in Slicer ({how}): {path}"


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
