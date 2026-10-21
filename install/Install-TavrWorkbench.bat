@echo off
rem Double-click to install 3D Slicer + TavrWorkbench (downloads and runs install_windows.ps1).
title TavrWorkbench installer
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/pcdslab/TavrWorkbench/main/install/install_windows.ps1 | iex"
echo.
pause
