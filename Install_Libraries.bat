@echo off
REM ======================================================================
REM  HKPM-HM v1.0 - one-time library installer (Windows)
REM
REM  Double-click this file ONCE. It finds your Python and installs
REM  every library the model needs, including the ones for shapefile
REM  and NetCDF input (geopandas, pyshp, xarray, netCDF4), directly
REM  into Windows for your user account. After it finishes you can
REM  simply double-click HKPM_HM_v1_0.py and everything will load.
REM ======================================================================
title HKPM-HM - install libraries

echo.
echo ======================================================================
echo  HKPM-HM v1.0  -  one-time library installation
echo ======================================================================
echo.

REM ---------- Step 1: find a usable Python ------------------------------
set "PYEXE="

echo [1/3] Looking for Python 3.10 or newer ...

REM The "py" launcher is what Windows uses when you double-click a .py file
where py >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
)

REM Standard per-user install locations
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"

REM System-wide locations
if not defined PYEXE if exist "C:\Python313\python.exe" set "PYEXE=C:\Python313\python.exe"
if not defined PYEXE if exist "C:\Python312\python.exe" set "PYEXE=C:\Python312\python.exe"
if not defined PYEXE if exist "C:\Python311\python.exe" set "PYEXE=C:\Python311\python.exe"

REM "python" on PATH - last, because on Windows 10/11 the default "python"
REM may be the Microsoft Store stub, which is not a real installation.
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
        echo %PYEXE% | findstr /i "WindowsApps" >nul && set "PYEXE="
    )
)

if not defined PYEXE (
    echo.
    echo   [ERROR] No real Python 3.10+ found on this computer.
    echo           Note: the "python" command on Windows 10/11 sometimes
    echo           opens the Microsoft Store - that is not a real Python.
    echo           Please install Python from https://www.python.org/downloads/
    echo           and TICK the box "Add python.exe to PATH", then run
    echo           this file again.
    echo.
    pause
    exit /b 1
)
echo      Using: %PYEXE%

REM ---------- Step 2: check the version ---------------------------------
echo.
echo [2/3] Checking the Python version ...
"%PYEXE%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo   [ERROR] Python 3.10 or newer is required. Found:
    "%PYEXE%" --version
    pause
    exit /b 1
)
"%PYEXE%" --version

REM ---------- Step 3: install every required library --------------------
echo.
echo [3/3] Installing all libraries (this can take a few minutes) ...
echo       numpy, pandas, matplotlib, scipy        - model core
echo       geopandas, pyshp                        - shapefile input
echo       xarray, netCDF4                         - NetCDF input
echo       openpyxl                                - Excel input
echo.

"%PYEXE%" -m pip install --upgrade pip
"%PYEXE%" -m pip install --upgrade numpy pandas matplotlib scipy geopandas pyshp xarray netCDF4 openpyxl
if errorlevel 1 (
    echo.
    echo   [ERROR] One or more libraries failed to install.
    echo           The most common causes are: no internet connection,
    echo           a proxy/firewall, or antivirus blocking pip.
    echo           Read the pip messages above for the exact reason.
    pause
    exit /b 1
)

REM ---------- Verify that every import actually works --------------------
echo.
echo Verifying the installation ...
"%PYEXE%" -c "import numpy, pandas, matplotlib, scipy, geopandas, shapefile, xarray, netCDF4, openpyxl, tkinter; print('  All libraries OK - shapefile, NetCDF and Excel input will work.')"
if errorlevel 1 (
    echo   [WARN] Verification failed for at least one library - see above.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo  DONE. You can now double-click  HKPM_HM_v1_0.py  to start the model.
echo  Shapefile, NetCDF, CSV and Excel inputs will all load correctly.
echo ======================================================================
echo.
pause
exit /b 0
