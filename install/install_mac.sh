#!/bin/bash
# TavrWorkbench one-step installer for macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/install/install_mac.sh | bash
#
# Installs 3D Slicer (latest stable, verified with its SHA-512), downloads TavrWorkbench from GitHub,
# adds it to Slicer's module paths and to the Favorite modules toolbar. Safe to run again: it then
# just updates TavrWorkbench and reuses the Slicer it installed before.
#
# Optional environment variables (put them before "bash", e.g. "... | TAVR_BRANCH=dev bash"):
#   TAVR_BRANCH=main         GitHub branch to install
#   SLICER_VERSION=5.12.4    install this Slicer release instead of the latest stable
#   TAVR_UPDATE_SLICER=1     download Slicer again even if one was installed before
set -euo pipefail

REPO="pcdslab/TavrWorkbench"
MODULE_NAME="TavrWorkbench"
BRANCH="${TAVR_BRANCH:-main}"
INSTALL_ROOT="$HOME/Library/Application Support/TavrWorkbench"
SOURCE_DIR="$INSTALL_ROOT/source"
MODULE_DIR="$SOURCE_DIR/$MODULE_NAME"
MARKER="$INSTALL_ROOT/slicer_app.txt"   # path of the Slicer.app this installer set up
LOG="$INSTALL_ROOT/install.log"
MIN_FREE_GB=4

mkdir -p "$INSTALL_ROOT"
exec > >(tee -a "$LOG") 2>&1
echo "===== TavrWorkbench installer, $(date) ====="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tavr-install.XXXXXX")"
MNT=""
SLICER_APP=""
cleanup() {
    if [ -n "$MNT" ]; then hdiutil detach "$MNT" -force -quiet >/dev/null 2>&1 || true; fi
    rm -rf "$WORK"
}
trap cleanup EXIT

say() { printf '\n==> %s\n' "$*"; }
die() {
    printf '\nERROR: %s\n' "$*" >&2
    printf 'A log of this run is in: %s\n' "$LOG" >&2
    exit 1
}

# JSON field via the JavaScript engine built into macOS (no python/jq needed)
json_get() {
    osascript -l JavaScript \
        -e 'function run(a){var v=JSON.parse(a[0])[a[1]];return (v===null||v===undefined)?"":String(v)}' \
        "$1" "$2"
}

download() {  # url, output file
    curl -fL --retry 5 --retry-delay 5 --connect-timeout 30 --progress-bar -o "$2" "$1"
}

plist_version() {
    /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$1/Contents/Info.plist" 2>/dev/null || true
}

# ---------------------------------------------------------------------------------------------
check_system() {
    [ "$(uname -s)" = "Darwin" ] || die "This installer is for macOS. On Windows use install_windows.ps1."
    local free_kb
    free_kb="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
    if [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
        die "Not enough free disk space: at least ${MIN_FREE_GB} GB is needed."
    fi
}

install_module() {
    say "Downloading TavrWorkbench ($BRANCH) from github.com/$REPO"
    download "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip" "$WORK/source.zip" \
        || die "Could not download TavrWorkbench. Check the internet connection."
    mkdir -p "$WORK/source"
    unzip -q "$WORK/source.zip" -d "$WORK/source" || die "The TavrWorkbench download is damaged."
    local top
    top="$(find "$WORK/source" -mindepth 1 -maxdepth 1 -type d -print -quit)"
    [ -f "$top/$MODULE_NAME/$MODULE_NAME.py" ] || die "Downloaded code has no $MODULE_NAME/$MODULE_NAME.py."
    [ -f "$top/install/configure_slicer.py" ] || die "Downloaded code has no install/configure_slicer.py."

    # Swap the new code in only once it is complete
    rm -rf "$SOURCE_DIR.new" "$SOURCE_DIR.old"
    ditto "$top" "$SOURCE_DIR.new"
    if [ -d "$SOURCE_DIR" ]; then mv "$SOURCE_DIR" "$SOURCE_DIR.old"; fi
    mv "$SOURCE_DIR.new" "$SOURCE_DIR"
    rm -rf "$SOURCE_DIR.old"
    echo "TavrWorkbench installed in: $SOURCE_DIR"
}

ensure_rosetta() {
    # Official Slicer builds for macOS are Intel builds; Apple Silicon Macs run them through Rosetta 2.
    [ "$(uname -m)" = "arm64" ] || return 0
    if arch -x86_64 /usr/bin/true >/dev/null 2>&1; then return 0; fi
    say "Installing Rosetta 2 (needed to run Slicer on Apple Silicon). You may be asked for your Mac password."
    softwareupdate --install-rosetta --agree-to-license \
        || sudo softwareupdate --install-rosetta --agree-to-license \
        || true
    arch -x86_64 /usr/bin/true >/dev/null 2>&1 || die "Rosetta 2 could not be installed."
}

install_slicer() {
    # Re-runs reuse the Slicer installed earlier (only TavrWorkbench is updated)
    if [ "${TAVR_UPDATE_SLICER:-0}" != "1" ] && [ -f "$MARKER" ]; then
        local previous
        previous="$(cat "$MARKER")"
        if [ -x "$previous/Contents/MacOS/Slicer" ]; then
            SLICER_APP="$previous"
            say "Using the Slicer installed earlier: $SLICER_APP"
            return 0
        fi
    fi

    say "Looking up the 3D Slicer release"
    local query="os=macosx&stability=release"
    if [ -n "${SLICER_VERSION:-}" ]; then query="$query&version=$SLICER_VERSION"; fi
    local info version url sha
    info="$(curl -fsSL --retry 5 --connect-timeout 30 "https://download.slicer.org/find?$query")" \
        || die "Could not reach download.slicer.org. Check the internet connection."
    version="$(json_get "$info" version)"
    url="$(json_get "$info" download_url)"
    sha="$(json_get "$info" sha512)"
    if [ -z "$url" ] || [ -z "$version" ]; then die "download.slicer.org did not return a macOS release."; fi
    case "$url" in http*) ;; *) url="https://download.slicer.org$url" ;; esac
    echo "Slicer $version"

    local apps="/Applications"
    if [ ! -w "$apps" ]; then apps="$HOME/Applications"; mkdir -p "$apps"; fi
    local dest="$apps/Slicer.app"
    # Never overwrite a different Slicer the user already has
    if [ -e "$dest" ] && [ "$(plist_version "$dest")" != "$version" ]; then dest="$apps/Slicer $version.app"; fi

    if [ -x "$dest/Contents/MacOS/Slicer" ] && [ "$(plist_version "$dest")" = "$version" ]; then
        echo "Slicer $version is already installed: $dest"
    else
        say "Downloading Slicer $version (about 450 MB)"
        download "$url" "$WORK/Slicer.dmg" || die "Could not download Slicer."
        if [ -n "$sha" ]; then
            local actual
            actual="$(shasum -a 512 "$WORK/Slicer.dmg" | awk '{print $1}')"
            [ "$actual" = "$sha" ] || die "The Slicer download is corrupted (checksum mismatch). Please run again."
            echo "Checksum OK"
        fi

        say "Installing Slicer into $apps"
        MNT="$WORK/mnt"
        mkdir -p "$MNT"
        # "yes" accepts the license page some disk images show
        { yes || true; } | hdiutil attach -nobrowse -noautoopen -readonly -mountpoint "$MNT" "$WORK/Slicer.dmg" >/dev/null \
            || die "Could not open the Slicer disk image."
        local src
        src="$(find "$MNT" -maxdepth 1 -name '*.app' -print -quit)"
        [ -n "$src" ] || die "No application found in the Slicer disk image."
        rm -rf "$dest"
        ditto "$src" "$dest" || die "Could not copy Slicer to $apps."
        hdiutil detach "$MNT" -quiet >/dev/null 2>&1 || hdiutil detach "$MNT" -force -quiet >/dev/null 2>&1 || true
        MNT=""
        xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
    fi
    [ -x "$dest/Contents/MacOS/Slicer" ] || die "Slicer was not installed correctly."
    SLICER_APP="$dest"
    echo "$SLICER_APP" >"$MARKER"
}

configure_slicer() {
    say "Adding TavrWorkbench to Slicer (module path + Favorite modules)"
    local result="$WORK/configure_result.txt" slicer_log="$WORK/configure_slicer.log"
    TAVR_MODULE_DIR="$MODULE_DIR" TAVR_RESULT_FILE="$result" \
        "$SLICER_APP/Contents/MacOS/Slicer" --no-splash --no-main-window --ignore-slicerrc \
        --disable-cli-modules --disable-scripted-loadable-modules \
        --python-script "$SOURCE_DIR/install/configure_slicer.py" >"$slicer_log" 2>&1 &
    local pid=$! waited=0 grace=0
    # First start of Slicer can take a while; stop waiting 20 s after the result is written
    while kill -0 "$pid" 2>/dev/null; do
        if [ -s "$result" ]; then grace=$((grace + 2)); fi
        if [ "$grace" -ge 20 ] || [ "$waited" -ge 600 ]; then break; fi
        sleep 2
        waited=$((waited + 2))
    done
    kill "$pid" 2>/dev/null || true
    pkill -f "configure_slicer.py" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true

    if [ -s "$result" ] && head -n 1 "$result" | grep -q '^OK'; then
        tail -n +2 "$result"
    else
        echo "----- Slicer output -----"
        cat "$slicer_log" 2>/dev/null || true
        cat "$result" 2>/dev/null || true
        die "Slicer could not be configured."
    fi
}

# ---------------------------------------------------------------------------------------------
check_system
install_module
ensure_rosetta
install_slicer
configure_slicer

say "Done. TavrWorkbench is ready."
echo "Start Slicer from: $SLICER_APP"
echo "TavrWorkbench is in the Favorite modules toolbar (and under Modules > Examples)."
echo "To update TavrWorkbench later, run the same install command again."

answer="n"
if read -r -p "Open Slicer now? [Y/n] " answer </dev/tty 2>/dev/null; then
    case "$answer" in [nN]*) ;; *) open "$SLICER_APP" ;; esac
fi
