# HKPM-HM — Hindu Kush Pamir Mountains Hydrological Model

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python ≥ 3.10](https://img.shields.io/badge/python-%E2%89%A5%203.10-blue.svg)](https://www.python.org/)

HKPM-HM is a conceptual, semi-distributed hydrological model developed for
data-scarce, snow- and glacier-dominated mountain catchments of the Hindu
Kush–Pamir region, and designed to work universally from Alpine glacierized
to lowland rainfall-dominated catchments. The complete model — numerical
core, calibration engine, and graphical user interface — ships as a single
Python file.

## Repository contents

| File / folder | Purpose |
|---|---|
| `HKPM_HM_v1_0.py` | The complete model (single file; opens a GUI when run) |
| `simulated_flows/` | **Simulated daily discharge for the 35 study catchments** of the accompanying paper (calibration + validation periods) — see [`simulated_flows/README.md`](simulated_flows/README.md) |
| `docs/HKPM_HM_Technical_Manual_and_User_Guide.pdf` | Combined technical manual and user guide (ESM 2 of the paper) |
| `Install_Libraries.bat` | One-click Windows installer for all required libraries |
| `INSTRUCTIONS.txt` | Step-by-step Windows installation and start-up guide |
| `requirements.txt` / `environment.yml` | Pinned pip / conda environments |
| `CITATION.cff` | Machine-readable citation metadata |

## Key features

- **14 model parameters with modular process activation** — snow,
  sublimation, interception, interflow, groundwater exchange, and glacier
  modules can each be switched on/off to match the catchment.
- **Process representation**: sigmoid rain/snow partitioning; elevation-band
  snow accumulation and degree-day melt with seasonal radiation factor;
  snow sublimation for cold-arid environments; external degree-day glacier
  melt (clean and debris-covered ice); Hargreaves–Samani evapotranspiration
  with soil-moisture stress; nonlinear soil-moisture runoff generation;
  three-pathway routing (quick flow / interflow / baseflow); groundwater
  exchange for gaining/losing streams.
- **Calibration**: Differential Evolution, PSO, SCE-UA, Adaptive DE, and
  Basin Hopping, with standard / extended / very-extended parameter bounds,
  spin-up initialization, and automatic convergence detection.
- **Graphical user interface** (tkinter) with tabs for Data, Elevation
  Bands, Periods, Calibration, Optimization, Glacier, Glacier Post-Cal,
  Ungauged, and Sensitivity.
- **Flexible input**: CSV, Excel (.xlsx) and NetCDF time series with
  automatic date-format detection; shapefile catchment boundaries and
  yearly glacier outlines.

## Software metadata

| | |
|---|---|
| Name | Hindu Kush Pamir Mountains Hydrological Model (HKPM-HM) |
| Version | 1.0.0 (first released 2026) |
| Language | Python ≥ 3.10 (developed and tested with 3.10–3.13) |
| Dependencies | numpy, pandas, matplotlib, geopandas, rasterio, shapely, scipy, openpyxl, tkinter (GUI); optional: xarray, netCDF4, pyshp |
| Operating systems | Windows / Linux / macOS |
| License | GNU General Public License v3.0 (GPL-3.0) |
| Runtime | a 30-year daily simulation completes in < 1 s on a standard desktop; runtime scales ≈ linearly with record length and number of elevation bands |

## Installation

### Option A — pip (all platforms)

```bash
pip install -r requirements.txt
```

`requirements.txt` pins the exact versions of the reference environment the
release was tested with. The model is not version-sensitive: any reasonably
recent releases of the listed packages work (indicative floors:
numpy ≥ 1.24, pandas ≥ 2.0, scipy ≥ 1.10, geopandas ≥ 0.13).

### Option B — conda

```bash
conda env create -f environment.yml
conda activate hkpm-hm
```

### Option C — Windows one-click

Double-click `Install_Libraries.bat` (finds your Python, installs and
verifies every library; no administrator rights needed). See
`INSTRUCTIONS.txt` for a step-by-step Windows guide.

## Quick start

```bash
python HKPM_HM_v1_0.py
```

The GUI opens; the workflow runs left to right across the tabs: load the
forcing and discharge data, define elevation bands and periods, calibrate,
validate, and export. A complete walk-through, the mathematical description
of every module, and the parameter tables are given in the combined
technical manual and user guide:

- [`docs/HKPM_HM_Technical_Manual_and_User_Guide.pdf`](docs/HKPM_HM_Technical_Manual_and_User_Guide.pdf)

## Simulated discharge for the 35 study catchments

The [`simulated_flows/`](simulated_flows/) folder provides the simulated
daily discharge (m³ s⁻¹) of all 35 Afghan study catchments of the
accompanying paper — one CSV per catchment, covering the calibration and
validation periods. Each series comes from the model configuration matching
the catchment's actual cryospheric status: 29 glacierized catchments are
simulated with the glacier module active, 6 glacier-free catchments without
it. Observed streamflow was provided by the Afghanistan Ministry of Energy
and Water (MEW) and is subject to MEW's data-sharing policy, so only the
simulated series are published here. Details and a per-catchment overview
table: [`simulated_flows/README.md`](simulated_flows/README.md).

## Related repository

The calibrated Google Earth Engine script used to derive the multi-temporal
glacier inventory (Landsat, 1986–2025) that forces the glacier module is
published separately:
**[HKPM-Glacier-Inventory-GEE](https://github.com/mnajimnasimi/HKPM-Glacier-Inventory-GEE)**

## Citation

If you use HKPM-HM in your research, please cite the accompanying paper
(reference will be added upon publication) and the software:

> Nasimi, M. N. (2026). *HKPM-HM — Hindu Kush Pamir Mountains Hydrological
> Model* (Version 1.0.0) [Computer software].
> https://github.com/mnajimnasimi/HKPM-HM

A machine-readable citation is provided in [`CITATION.cff`](CITATION.cff).

## License

Released under the [GNU General Public License v3.0](LICENSE).

## Contact

Mohammad Najim Nasimi
Chair of Hydrology and River Basin Management (Prof. Disse),
Technical University of Munich — najim.nasimi@tum.de
