# TavrWorkbench one-step installer for Windows (Windows PowerShell 5.1 or PowerShell 7).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/install/install_windows.ps1 | iex"
#
# Installs 3D Slicer (latest stable, verified with its SHA-512) for the current user, downloads
# TavrWorkbench from GitHub, adds it to Slicer's module paths and to the Favorite modules toolbar.
# Safe to run again: it then just updates TavrWorkbench and reuses the Slicer it installed before.
#
# Optional environment variables (set before running, e.g.  $env:TAVR_BRANCH = "dev"):
#   TAVR_BRANCH=main         GitHub branch to install
#   SLICER_VERSION=5.12.4    install this Slicer release instead of the latest stable
#   TAVR_UPDATE_SLICER=1     download Slicer again even if one was installed before

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # the PS 5.1 progress bar makes downloads very slow
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $Repo = 'pcdslab/TavrWorkbench'
    $ModuleName = 'TavrWorkbench'
    $Branch = if ($env:TAVR_BRANCH) { $env:TAVR_BRANCH } else { 'main' }
    $InstallRoot = Join-Path $env:LOCALAPPDATA 'TavrWorkbench'
    $SourceDir = Join-Path $InstallRoot 'source'
    $ModuleDir = Join-Path $SourceDir $ModuleName
    $Marker = Join-Path $InstallRoot 'slicer_exe.txt'   # path of the Slicer.exe this installer set up
    $LogFile = Join-Path $InstallRoot 'install.log'
    $MinFreeGB = 4

    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    $Work = Join-Path ([IO.Path]::GetTempPath()) ('tavr-install-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $Work | Out-Null

    function Write-Step([string]$Text) { Write-Host ''; Write-Host "==> $Text" -ForegroundColor Cyan }

    function Get-Download([string]$Url, [string]$OutFile) {
        # curl.exe ships with Windows 10 1803+ and is faster and more robust than Invoke-WebRequest
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            & $curl.Source -fL --retry 5 --retry-delay 5 --connect-timeout 30 --progress-bar -o $OutFile $Url
            if ($LASTEXITCODE -eq 0) { return }
            Write-Warning "curl.exe failed (exit code $LASTEXITCODE), trying again with Invoke-WebRequest"
        }
        for ($i = 1; $i -le 3; $i++) {
            try { Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing; return }
            catch { if ($i -eq 3) { throw "Could not download $Url : $($_.Exception.Message)" }; Start-Sleep -Seconds 5 }
        }
    }

    # ------------------------------------------------------------------------------------------
    function Test-System {
        $drive = (Get-Item $env:LOCALAPPDATA).PSDrive
        if ($drive.Free -lt ($MinFreeGB * 1GB)) {
            throw "Not enough free disk space on $($drive.Name): at least $MinFreeGB GB is needed."
        }
    }

    function Install-TavrModule {
        Write-Step "Downloading TavrWorkbench ($Branch) from github.com/$Repo"
        $zip = Join-Path $Work 'source.zip'
        Get-Download "https://github.com/$Repo/archive/refs/heads/$Branch.zip" $zip
        $extract = Join-Path $Work 'source'
        Expand-Archive -Path $zip -DestinationPath $extract -Force
        $top = Get-ChildItem -Path $extract -Directory | Select-Object -First 1
        if (-not $top -or -not (Test-Path (Join-Path $top.FullName "$ModuleName\$ModuleName.py"))) {
            throw "Downloaded code has no $ModuleName\$ModuleName.py."
        }
        if (-not (Test-Path (Join-Path $top.FullName 'install\configure_slicer.py'))) {
            throw "Downloaded code has no install\configure_slicer.py."
        }
        # Swap the new code in only once it is complete
        $new = "$SourceDir.new"; $old = "$SourceDir.old"
        foreach ($d in @($new, $old)) { if (Test-Path $d) { Remove-Item $d -Recurse -Force } }
        Copy-Item -Path $top.FullName -Destination $new -Recurse
        if (Test-Path $SourceDir) { Rename-Item $SourceDir $old }
        Rename-Item $new $SourceDir
        if (Test-Path $old) { Remove-Item $old -Recurse -Force }
        Write-Host "TavrWorkbench installed in: $SourceDir"
    }

    function Install-Slicer {
        # Re-runs reuse the Slicer installed earlier (only TavrWorkbench is updated)
        if ($env:TAVR_UPDATE_SLICER -ne '1' -and (Test-Path $Marker)) {
            $previous = (Get-Content $Marker -Raw).Trim()
            if ($previous -and (Test-Path $previous)) {
                Write-Step "Using the Slicer installed earlier: $previous"
                return $previous
            }
        }

        Write-Step 'Looking up the 3D Slicer release'
        $query = 'os=win&stability=release'
        if ($env:SLICER_VERSION) { $query += "&version=$($env:SLICER_VERSION)" }
        $info = Invoke-RestMethod -Uri "https://download.slicer.org/find?$query" -UseBasicParsing
        if (-not $info.download_url -or -not $info.version) { throw 'download.slicer.org did not return a Windows release.' }
        $url = [string]$info.download_url
        if ($url -notmatch '^https?://') { $url = "https://download.slicer.org$url" }
        $version = [string]$info.version
        Write-Host "Slicer $version"

        $slicerDir = Join-Path $env:LOCALAPPDATA "slicer.org\Slicer $version"
        $slicerExe = Join-Path $slicerDir 'Slicer.exe'
        if (Test-Path $slicerExe) {
            Write-Host "Slicer $version is already installed: $slicerDir"
        } else {
            Write-Step "Downloading Slicer $version (about 300-450 MB)"
            $setup = Join-Path $Work 'Slicer-setup.exe'
            Get-Download $url $setup
            if ($info.sha512) {
                $actual = (Get-FileHash -Path $setup -Algorithm SHA512).Hash.ToLower()
                if ($actual -ne ([string]$info.sha512).ToLower()) {
                    throw 'The Slicer download is corrupted (checksum mismatch). Please run the installer again.'
                }
                Write-Host 'Checksum OK'
            }
            Write-Step "Installing Slicer $version for the current user (takes a few minutes)"
            # NSIS installer: /S = silent, /D = target folder (must be last and unquoted)
            $proc = Start-Process -FilePath $setup -ArgumentList "/S /D=$slicerDir" -Wait -PassThru
            if (-not (Test-Path $slicerExe)) { throw "Slicer installation failed (installer exit code $($proc.ExitCode))." }
        }
        Set-Content -Path $Marker -Value $slicerExe -Encoding UTF8
        return $slicerExe
    }

    function Set-SlicerConfiguration([string]$SlicerExe) {
        Write-Step 'Adding TavrWorkbench to Slicer (module path + Favorite modules)'
        $result = Join-Path $Work 'configure_result.txt'
        $script = Join-Path $SourceDir 'install\configure_slicer.py'
        $env:TAVR_MODULE_DIR = $ModuleDir
        $env:TAVR_RESULT_FILE = $result
        $slicerArgs = "--no-splash --no-main-window --ignore-slicerrc --disable-cli-modules " +
                      "--disable-scripted-loadable-modules --python-script `"$script`""
        $proc = Start-Process -FilePath $SlicerExe -ArgumentList $slicerArgs -PassThru -WindowStyle Hidden
        # First start of Slicer can take a while; stop waiting 20 s after the result is written
        $waited = 0; $grace = 0
        while (-not $proc.HasExited) {
            if ((Test-Path $result) -and (Get-Item $result).Length -gt 0) { $grace += 2 }
            if ($grace -ge 20 -or $waited -ge 600) { break }
            Start-Sleep -Seconds 2; $waited += 2
        }
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*configure_slicer.py*' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Remove-Item Env:TAVR_MODULE_DIR, Env:TAVR_RESULT_FILE -ErrorAction SilentlyContinue

        $text = if (Test-Path $result) { Get-Content $result -Raw } else { '' }
        if ($text -notmatch '^OK') { throw "Slicer could not be configured.`n$text" }
        Write-Host (($text -split "`n" | Select-Object -Skip 1) -join "`n").Trim()
    }

    # ------------------------------------------------------------------------------------------
    $transcript = $false
    try { Start-Transcript -Path $LogFile -Append | Out-Null; $transcript = $true } catch { }
    try {
        Test-System
        Install-TavrModule
        $slicerExe = Install-Slicer
        Set-SlicerConfiguration $slicerExe

        Write-Step 'Done. TavrWorkbench is ready.'
        Write-Host "Start Slicer from the Start menu (3D Slicer) or: $slicerExe"
        Write-Host 'TavrWorkbench is in the Favorite modules toolbar (and under Modules > Examples).'
        Write-Host 'To update TavrWorkbench later, run the same install command again.'
        $answer = Read-Host 'Open Slicer now? [Y/n]'
        if ($answer -notmatch '^[nN]') { Start-Process -FilePath $slicerExe }
    }
    catch {
        Write-Host ''
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "A log of this run is in: $LogFile"
    }
    finally {
        if ($transcript) { try { Stop-Transcript | Out-Null } catch { } }
        Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
    }
}
