# Installing 3D Slicer + TavrWorkbench

One command installs everything: 3D Slicer (latest stable release), the TavrWorkbench module, and the
Slicer settings so TavrWorkbench appears in the **Favorite modules** toolbar. It needs an internet
connection, about 4 GB of free disk space, and 10–20 minutes (Slicer is a ~450 MB download).

Run the same command again at any time to **update TavrWorkbench**; Slicer is not downloaded again.

## macOS

1. Open **Terminal** (press `⌘ Space`, type *Terminal*, press Enter).
2. Copy this line, paste it into Terminal and press Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/install/install_mac.sh | bash
   ```

3. On Apple Silicon Macs (M1/M2/M3/M4) you may be asked for your Mac password once, to install Rosetta 2,
   which Slicer needs. Typing the password shows no characters; that is normal.
4. When it says **Done**, answer `Y` to open Slicer.

## Windows

1. Open **PowerShell** (press the `Windows` key, type *PowerShell*, press Enter). No administrator rights needed.
2. Copy this line, paste it into PowerShell (right-click pastes) and press Enter:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/install/install_windows.ps1 | iex"
   ```

3. When it says **Done**, press Enter to open Slicer. Slicer is also in the Start menu as *3D Slicer*.

Alternative: download [`Install-TavrWorkbench.bat`](Install-TavrWorkbench.bat) and double-click it. If Windows
shows "Windows protected your PC", click **More info → Run anyway**.

## Where things go

|                 | macOS                                                     | Windows                                   |
|-----------------|-----------------------------------------------------------|-------------------------------------------|
| 3D Slicer       | `/Applications/Slicer.app` (or `~/Applications`)          | `%LOCALAPPDATA%\slicer.org\Slicer <version>` |
| TavrWorkbench   | `~/Library/Application Support/TavrWorkbench/source`      | `%LOCALAPPDATA%\TavrWorkbench\source`     |
| Install log     | `~/Library/Application Support/TavrWorkbench/install.log` | `%LOCALAPPDATA%\TavrWorkbench\install.log` |

An existing `Slicer.app` of a different version is left alone; the new one is installed as `Slicer <version>.app`.

TavrWorkbench is loaded by a short, clearly marked block in Slicer's startup file in your home folder
(`~/.slicerrc.py` on macOS, `%USERPROFILE%\.slicerrc.py` on Windows). Deleting that block unloads it.

## Options (for the developers)

Set before running (macOS: `... | TAVR_BRANCH=dev bash`; Windows: `$env:TAVR_BRANCH="dev"` first):

| Variable              | Effect                                                    |
|-----------------------|-----------------------------------------------------------|
| `TAVR_BRANCH`         | GitHub branch to install (default `main`)                 |
| `SLICER_VERSION`      | Install this Slicer release, e.g. `5.12.4`                |
| `TAVR_UPDATE_SLICER=1`| Download and install Slicer again                         |

## Troubleshooting

Send the install log (paths above) to the TavrWorkbench team. Common causes:

* **No internet / proxy**: the installer needs `github.com`, `raw.githubusercontent.com` and `download.slicer.org`.
* **"checksum mismatch"**: the download was interrupted; run the command again.
* **TavrWorkbench missing in Slicer**: run the command again, or in Slicer open
  *Edit → Application Settings → Modules* and check that the TavrWorkbench folder is listed under
  *Additional module paths*.
