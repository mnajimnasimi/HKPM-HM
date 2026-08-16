#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
HKPM-HM UNIVERSAL v1.0 - HYDROLOGICAL MODEL
================================================================================

Version: 1.0.0

Author: Mohammad Najim Nasimi
        Chair of Hydrology and River Basin Management (Prof. Disse)
        Technical University of Munich

UNIVERSAL MODEL - Works from Alpine glacierized to Lowland rainfall-dominated
================================================================================

Key Features:
    - 14 model parameters with modular activation
    - NEW: Interception module for forests (Imax parameter)
    - NEW: Hargreaves-Samani ET estimation (critical for lowlands!)
    - NEW: Interflow pathway (Ki parameter) - three-layer routing
    - NEW: Groundwater exchange for gaining/losing streams (GWexch)
    - NEW: ET correction factor (ETmult) for regional calibration
    - NEW: Catchment type selector (Alpine/Lowland/Universal)
    - NEW: Optional snow module - can be disabled for warm catchments
    - Extended parameter bounds: Standard, Extended, Very Extended
    - Multiple optimization methods: DE, PSO, SCE-UA, Adaptive DE, Basin Hopping
    - Robust CSV/NetCDF data loading with auto date format detection
    - Spin-up period for proper state initialization
    - Automatic convergence detection & early stopping
    - Iteration history with parameter selection
    - Ungauged catchment modeling
    - Integrated glacier melt model with post-calibration tuning
    - Sensitivity analysis
    - Export functionality for all results
    
FEATURES:
    - Works for ANY catchment worldwide (Alpine to Lowland)
    - Proper ET estimation - crucial for rainfall-dominated catchments
    - Three runoff pathways: Quick + Interflow + Baseflow
    - Interception for forested catchments
    - Groundwater exchange for gaining/losing streams
    - Modular design - enable/disable snow, glacier, interception
    - Extended parameter bounds for challenging catchments
    - Robust date parsing for various CSV formats
    - Run with spinup for proper state initialization

GitHub: https://github.com/mnajimnasimi/HKPM-HM

LICENSE: All Rights Reserved
Copyright (c) 2026 Mohammad Najim Nasimi
Chair of Hydrology and River Basin Management (Prof. Disse)
Technical University of Munich

This software is proprietary. No modification, copying, or redistribution 
is allowed. Academic/research use only with MANDATORY CITATION:

    Nasimi, M. N. (2026). Hindu Kush Pamir Mountains Hydrological Model 
    (HKPM-HM) (Version 1.0). Chair of Hydrology and River Basin Management,
    Technical University of Munich. https://github.com/mnajimnasimi/HKPM-HM
================================================================================
"""

import sys
import os
import json
import pickle
import glob
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
import threading
import webbrowser
import time

import numpy as np
import pandas as pd

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Plotting
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator, AutoLocator

# Optimization
from scipy.optimize import differential_evolution, minimize, basinhopping
try:
    from scipy.stats import qmc
    HAS_QMC = True
except ImportError:
    HAS_QMC = False

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

# Optional imports
try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    import shapefile as shpfile  # pyshp - pure Python, no binary deps
    HAS_PYSHP = True
except ImportError:
    HAS_PYSHP = False

try:
    import xarray as xr
    HAS_XARRAY = True
except ImportError:
    HAS_XARRAY = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# =============================================================================
# MODULE ALIASES FOR PICKLE COMPATIBILITY
# -----------------------------------------------------------------------------
# Saved model files (.pkl) store the module name that was active when they
# were written. Registering this module under its historical script names
# lets pickles saved by any earlier (or renamed) version load correctly.
# =============================================================================

_THIS_MODULE = sys.modules[__name__]
for _alias in (
    "HKPM_HM_v1_0_Universal_Sublimation_auto",
    "HKPM_HM_v1_0_Universal_Sublimation_auto_adv",
    "HKPM_HM_v1_0_Universal_Sublimation_auto_adv_withoutvalid",
    "HKPM_HM_v1_0_Universal_Sublimation_auto_adv_with_valid_manual",
    "HKPM_HM_v1_0",
):
    sys.modules.setdefault(_alias, _THIS_MODULE)

# =============================================================================
# CONSTANTS AND METADATA
# =============================================================================

APP_NAME = "HKPM-HM Universal - Hydrological Model"
APP_SHORT_NAME = "HKPM-HM"
APP_VERSION = "1.0.0"
AUTHOR = "Mohammad Najim Nasimi"
AFFILIATION = "Chair of Hydrology and River Basin Management (Prof. Disse), Technical University of Munich"
GITHUB_URL = "https://github.com/mnajimnasimi/HKPM-HM"

SECONDS_PER_DAY = 86400
DEFAULT_LAPSE_RATE = 6.5

# Plotting style
plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['font.size'] = 9
plt.rcParams['figure.dpi'] = 100
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_csv_timeseries(filepath, date_col=None, value_col=None):
    """Load time series from CSV with robust date parsing and column detection."""
    df = pd.read_csv(filepath)
    
    # Find date column
    if date_col is None or date_col not in df.columns:
        date_candidates = ['Date', 'date', 'DATE', 'time', 'Time', 'datetime', 'Datetime', 'DATETIME']
        for col in date_candidates:
            if col in df.columns:
                date_col = col
                break
        if date_col is None:
            date_col = df.columns[0]
    
    # Try multiple date formats
    date_formats = [
        '%Y-%m-%d',           # 2007-01-01
        '%Y-%m-%d %H:%M:%S',  # 2007-01-01 00:00:00
        '%d%b%Y %H:%M',       # 01Jan2007 00:00 (HEC-HMS)
        '%d%b%Y',             # 01Jan2007
        '%d/%m/%Y',           # 01/01/2007
        '%m/%d/%Y',           # 01/01/2007 (US)
        '%d-%m-%Y',           # 01-01-2007
        '%m-%d-%Y',           # 01-01-2007 (US)
        '%Y/%m/%d',           # 2007/01/01
        '%d.%m.%Y',           # 01.01.2007
    ]
    
    parsed = None
    for fmt in date_formats:
        try:
            parsed = pd.to_datetime(df[date_col], format=fmt)
            break
        except:
            continue
    
    if parsed is None:
        # Final fallback - let pandas infer
        parsed = pd.to_datetime(df[date_col], errors='coerce')
    
    df['_Date'] = parsed
    
    # Remove rows with invalid dates
    valid_mask = df['_Date'].notna()
    if not valid_mask.all():
        n_invalid = (~valid_mask).sum()
        print(f"Warning: {n_invalid} rows with invalid dates removed from {filepath}")
        df = df[valid_mask].copy()
    
    # Find value column
    if value_col is None or value_col not in df.columns:
        value_candidates = [
            'Precipitation_mm', 'precipitation', 'precip', 'Precip', 'PPT', 'ppt', 'P', 'p', 'pr',
            'Temperature_degC', 'Temperature', 'temperature', 'temp', 'Temp', 'T', 't', 'Tair',
            'Streamflow', 'streamflow', 'Flow', 'flow', 'Q', 'q', 'discharge', 'Discharge',
            'Glacier_Melt_m3_s', 'glacier_melt', 'GlacierMelt', 'melt',
            'Mean', 'mean', 'Value', 'value'
        ]
        for col in value_candidates:
            if col in df.columns:
                value_col = col
                break
        
        if value_col is None:
            for col in df.columns:
                if col not in [date_col, '_Date', 'Year', 'year', 'Month', 'month', 'DOY', 'doy', 'Day', 'day']:
                    if df[col].dtype in ['float64', 'int64', 'float32', 'int32']:
                        value_col = col
                        break
    
    if value_col is None:
        raise ValueError(f"Could not identify value column in {filepath}")
    
    series = pd.Series(df[value_col].values, index=df['_Date']).sort_index()
    
    # Handle duplicates by keeping first
    if series.index.duplicated().any():
        series = series[~series.index.duplicated(keep='first')]
    
    return series


def load_netcdf_timeseries(filepath, variable=None):
    """Load time series from NetCDF with spatial averaging."""
    if not HAS_XARRAY:
        raise ImportError("xarray and netCDF4 required for NetCDF files")
    
    ds = xr.open_dataset(filepath)
    
    if variable is None:
        for v in ['temperature', 'temp', 'Tair_f_inst', 't2m', 'tas', 
                  'precipitation', 'precip', 'pr', 'tp', 'Mean', 'mean']:
            if v in ds.data_vars:
                variable = v
                break
        if variable is None:
            variable = list(ds.data_vars)[0]
    
    times = pd.to_datetime(ds['time'].values)
    data = ds[variable].values
    
    if data.ndim > 1:
        data = np.nanmean(data, axis=tuple(range(1, data.ndim)))
    
    ds.close()
    return pd.Series(data, index=times).sort_index()


def load_timeseries(filepath, value_col=None):
    """Universal time series loader."""
    fp = str(filepath)
    if fp.lower().endswith(('.nc', '.nc4', '.netcdf')):
        return load_netcdf_timeseries(fp)
    return load_csv_timeseries(fp, value_col=value_col)


def load_elevation_bands(filepath):
    """Load elevation bands from CSV or Excel file."""
    fp = str(filepath)
    
    if fp.lower().endswith(('.xlsx', '.xls')):
        if not HAS_OPENPYXL:
            raise ImportError("openpyxl required for Excel files")
        df = pd.read_excel(fp)
    else:
        df = pd.read_csv(fp)
    
    col_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'mean' in col_lower and 'elev' in col_lower:
            col_map[col] = 'elev_mean'
        elif 'min' in col_lower and 'elev' in col_lower:
            col_map[col] = 'elev_min'
        elif 'max' in col_lower and 'elev' in col_lower:
            col_map[col] = 'elev_max'
        elif 'area' in col_lower and 'km' in col_lower:
            col_map[col] = 'area_km2'
        elif 'area' in col_lower and 'percent' in col_lower:
            col_map[col] = 'area_percent'
    
    df = df.rename(columns=col_map)
    
    if 'elev_mean' not in df.columns:
        if 'elev_min' in df.columns and 'elev_max' in df.columns:
            df['elev_mean'] = (df['elev_min'] + df['elev_max']) / 2
    
    return df


def extract_shapefile_info(filepath):
    """Extract catchment area and centroid from shapefile.
    Uses geopandas if available, falls back to pyshp (pure Python)."""
    
    # Method 1: geopandas (full functionality)
    if HAS_GEOPANDAS:
        try:
            gdf = gpd.read_file(filepath)
            if gdf.crs and gdf.crs.is_projected:
                gdf_proj = gdf
            else:
                gdf_proj = gdf.to_crs('EPSG:32642')
            
            area_m2 = gdf_proj.geometry.area.sum()
            
            try:
                merged = gdf_proj.geometry.union_all()
            except AttributeError:
                merged = gdf_proj.geometry.unary_union
            centroid_proj = merged.centroid
            centroid_gdf = gpd.GeoDataFrame(geometry=[centroid_proj], crs=gdf_proj.crs)
            centroid_wgs = centroid_gdf.to_crs('EPSG:4326').geometry.iloc[0]
            
            return {'area_km2': area_m2/1e6, 'latitude': centroid_wgs.y, 'longitude': centroid_wgs.x}
        except Exception:
            pass  # Fall through to pyshp
    
    # Method 2: pyshp fallback (pure Python, no binary dependencies)
    if HAS_PYSHP:
        try:
            sf = shpfile.Reader(filepath)
            
            # Read .prj file to determine if projected or geographic
            prj_path = filepath.replace('.shp', '.prj')
            is_projected = False
            is_utm = False
            utm_zone = None
            if os.path.exists(prj_path):
                with open(prj_path, 'r') as f:
                    prj_text = f.read()
                is_projected = 'PROJCS' in prj_text
                # Detect UTM zone
                import re
                utm_match = re.search(r'UTM[_ ]zone[_ ](\d+)', prj_text, re.IGNORECASE)
                if utm_match:
                    is_utm = True
                    utm_zone = int(utm_match.group(1))
            
            # Compute area using Shoelace formula on all polygon parts
            total_area_m2 = 0.0
            all_x, all_y = [], []
            
            for shape in sf.shapes():
                if shape.shapeType not in (5, 15, 25):  # Polygon types
                    continue
                parts = list(shape.parts) + [len(shape.points)]
                for i in range(len(parts) - 1):
                    ring = shape.points[parts[i]:parts[i+1]]
                    if len(ring) < 3:
                        continue
                    
                    # Shoelace formula for polygon area
                    n = len(ring)
                    area = 0.0
                    for j in range(n):
                        x1, y1 = ring[j]
                        x2, y2 = ring[(j + 1) % n]
                        area += x1 * y2 - x2 * y1
                    area = abs(area) / 2.0
                    
                    # First ring is outer boundary (positive), holes subtract
                    if i == 0 or parts[i] == shape.parts[0 if i == 0 else i]:
                        total_area_m2 += area
                    
                    for pt in ring:
                        all_x.append(pt[0])
                        all_y.append(pt[1])
            
            if total_area_m2 == 0 or not all_x:
                return None
            
            # Compute centroid from bounding box center
            cx = (min(all_x) + max(all_x)) / 2.0
            cy = (min(all_y) + max(all_y)) / 2.0
            
            if is_projected:
                # Coordinates are in meters → area is in m²
                area_km2 = total_area_m2 / 1e6
                
                # Convert centroid from UTM to approximate lat/lon
                if is_utm and utm_zone:
                    # Approximate UTM to WGS84 conversion
                    import math
                    lon0 = (utm_zone - 1) * 6 - 180 + 3  # Central meridian
                    # Simplified inverse UTM (good enough for centroid)
                    easting = cx - 500000  # Remove false easting
                    northing = cy
                    lat_approx = northing / 111320.0
                    lon_approx = lon0 + easting / (111320.0 * math.cos(math.radians(lat_approx)))
                    return {'area_km2': area_km2, 'latitude': lat_approx, 'longitude': lon_approx}
                else:
                    # Projected but unknown → return area, centroid in projected coords
                    # User may need to manually enter lat/lon
                    return {'area_km2': area_km2, 'latitude': cy, 'longitude': cx,
                            '_note': 'Centroid in projected CRS - verify lat/lon manually'}
            else:
                # Geographic coordinates (degrees) → need to convert area
                import math
                lat_center = cy
                # Approximate area conversion: 1 degree ≈ 111.32 km at equator
                # Adjusted for latitude
                m_per_deg_lat = 111320.0
                m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_center))
                area_m2_approx = total_area_m2 * m_per_deg_lat * m_per_deg_lon
                area_km2 = area_m2_approx / 1e6
                
                return {'area_km2': area_km2, 'latitude': cy, 'longitude': cx}
        except Exception:
            return None
    
    return None


# =============================================================================
# ELEVATION BANDS CLASS
# =============================================================================

class ElevationBands:
    """Manage elevation bands for semi-distributed modeling."""
    
    MAX_BANDS = 15
    
    def __init__(self):
        self.bands = None
        self.n_bands = 0
        self.ref_elevation = None
        self.total_area = 0
    
    def load_from_file(self, filepath):
        df = load_elevation_bands(filepath)
        self._process_bands(df)
        return self.get_summary()
    
    def set_manual(self, elevations, areas=None, area_percents=None):
        if areas is None and area_percents is None:
            raise ValueError("Provide either areas or area_percents")
        
        df = pd.DataFrame({'elev_mean': elevations})
        if areas is not None:
            df['area_km2'] = areas
        else:
            df['area_percent'] = area_percents
        
        self._process_bands(df)
    
    def _process_bands(self, df):
        if len(df) > self.MAX_BANDS:
            df = df.head(self.MAX_BANDS)
        
        if 'area_km2' in df.columns:
            self.total_area = df['area_km2'].sum()
            df['area_frac'] = df['area_km2'] / self.total_area
        else:
            df['area_frac'] = df['area_percent'] / 100.0
            self.total_area = None
        
        self.bands = df[['elev_mean', 'area_frac']].copy()
        if 'area_km2' in df.columns:
            self.bands['area_km2'] = df['area_km2']
        
        self.n_bands = len(self.bands)
        self.ref_elevation = np.average(self.bands['elev_mean'], weights=self.bands['area_frac'])
    
    def adjust_temperature(self, temp, lapse_rate=DEFAULT_LAPSE_RATE):
        if self.bands is None:
            return temp.reshape(-1, 1)
        
        temp = np.array(temp).reshape(-1, 1)
        elev_diff = self.bands['elev_mean'].values - self.ref_elevation
        temp_adj = lapse_rate * elev_diff / 1000
        
        return temp - temp_adj
    
    def get_summary(self):
        if self.bands is None:
            return {'n_bands': 0, 'ref_elev': None}
        
        return {
            'n_bands': self.n_bands,
            'ref_elev': self.ref_elevation,
            'elev_min': self.bands['elev_mean'].min(),
            'elev_max': self.bands['elev_mean'].max(),
            'total_area': self.total_area
        }
    
    def get_bands_table(self):
        if self.bands is None:
            return "No elevation bands loaded"
        
        lines = ["Band  Elev(m)  Area(%)"]
        lines.append("-" * 25)
        for i, row in self.bands.iterrows():
            area_pct = row['area_frac'] * 100
            lines.append(f"{i+1:4d}  {row['elev_mean']:7.0f}  {area_pct:6.1f}")
        return "\n".join(lines)
    
    def clear(self):
        self.bands = None
        self.n_bands = 0
        self.ref_elevation = None
        self.total_area = 0


# =============================================================================
# GLACIER MELT MODEL WITH YEARLY SUPPORT
# =============================================================================

class GlacierMeltModel:
    """Degree-day glacier melt model with debris-covered and clean ice."""
    
    PARAM_NAMES = ['ddf_clean', 'ddf_debris', 'lapse_rate', 't_melt', 'ref_elev']
    PARAM_BOUNDS = [(3.0, 12.0), (1.0, 8.0), (4.0, 8.0), (-2.0, 2.0), (2500, 5000)]
    
    def __init__(self):
        self.params = {
            'ddf_clean': 6.0, 'ddf_debris': 3.0, 'lapse_rate': 6.0,
            't_melt': 0.0, 'ref_elev': 3400
        }
        self.glacier_data = None
        self.elevation_bands = None
        self.yearly_bands = {}  # Store bands for each year
        self.total_area = 0
        self.n_glaciers = 0
        self.mode = 'single'  # 'single' or 'yearly'
    
    def load_glacier_shapefile(self, filepath):
        """Load single glacier shapefile."""
        if not HAS_GEOPANDAS:
            raise ImportError("geopandas required for glacier shapefiles.\nInstall: pip install pyshp geopandas")
        
        gdf = gpd.read_file(filepath)
        glaciers = []
        
        for _, glacier in gdf.iterrows():
            mean_elev = self._get_attr(glacier, ['mean_elev', 'Mean_elev', 'Zmed'], 5000)
            min_elev = self._get_attr(glacier, ['min_elev', 'Min_elev', 'Zmin'], 4000)
            max_elev = self._get_attr(glacier, ['max_elev', 'Max_elev', 'Zmax'], 6000)
            area_km2 = self._get_attr(glacier, ['area_km2', 'Area_km2', 'AREA'], 0.1)
            
            is_debris = any('debris' in str(glacier.get(c, '')).lower() 
                          for c in ['glacier_ty', 'type', 'Type'])
            
            if area_km2 > 0:
                glaciers.append({
                    'min_elev': min_elev, 'max_elev': max_elev, 'mean_elev': mean_elev,
                    'area_km2': area_km2, 'is_debris': is_debris
                })
        
        self.glacier_data = pd.DataFrame(glaciers)
        self._create_elevation_bands()
        self.total_area = self.glacier_data['area_km2'].sum()
        self.n_glaciers = len(self.glacier_data)
        self.mode = 'single'
        
        return {'n_glaciers': self.n_glaciers, 'total_area': self.total_area, 'mode': 'single'}
    
    def load_yearly_folder(self, folder_path, start_year, end_year):
        """Load yearly glacier shapefiles from folder structure."""
        if not HAS_GEOPANDAS:
            raise ImportError("geopandas required for glacier shapefiles.\nInstall: pip install geopandas")
        
        self.yearly_bands = {}
        years_loaded = 0
        
        for year in range(start_year, end_year + 1):
            year_folder = os.path.join(folder_path, str(year))
            if not os.path.exists(year_folder):
                continue
            
            glaciers = self._load_glaciers_from_folder(year_folder)
            if glaciers is not None and len(glaciers) > 0:
                bands = self._create_bands_from_glaciers(glaciers)
                self.yearly_bands[year] = {
                    'centers': bands[0],
                    'debris_areas': bands[1],
                    'clean_areas': bands[2],
                    'total_area': glaciers['area_km2'].sum()
                }
                years_loaded += 1
        
        if years_loaded == 0:
            raise ValueError("No yearly glacier data found")
        
        # Set average for single-mode fallback
        self.total_area = np.mean([b['total_area'] for b in self.yearly_bands.values()])
        self.n_glaciers = years_loaded
        self.mode = 'yearly'
        
        return {'years_loaded': years_loaded, 'total_area': self.total_area, 'mode': 'yearly'}
    
    def _load_glaciers_from_folder(self, year_folder):
        """Load glaciers from a year folder."""
        # Try combined file first
        for pattern in ['*_all.shp', '*_all_*.shp', '*combined*.shp']:
            files = glob.glob(os.path.join(year_folder, pattern))
            if files:
                try:
                    gdf = gpd.read_file(files[0])
                    if len(gdf) > 0:
                        return self._gdf_to_glaciers(gdf)
                except:
                    pass
        
        # Try separate clean_ice and debris files
        glacier_list = []
        for pattern, g_type in [('*clean_ice*.shp', False), ('*debris*.shp', True)]:
            files = glob.glob(os.path.join(year_folder, pattern))
            if files:
                try:
                    gdf = gpd.read_file(files[0])
                    for _, g in gdf.iterrows():
                        glacier_list.append(self._extract_glacier(g, g_type))
                except:
                    pass
        
        if glacier_list:
            return pd.DataFrame(glacier_list)
        
        # Try any shapefile
        files = glob.glob(os.path.join(year_folder, '*.shp'))
        if files:
            try:
                gdf = gpd.read_file(files[0])
                return self._gdf_to_glaciers(gdf)
            except:
                pass
        
        return None
    
    def _gdf_to_glaciers(self, gdf):
        glaciers = []
        for _, g in gdf.iterrows():
            is_debris = any('debris' in str(g.get(c, '')).lower() 
                          for c in ['glacier_ty', 'type', 'Type'])
            glaciers.append(self._extract_glacier(g, is_debris))
        return pd.DataFrame(glaciers)
    
    def _extract_glacier(self, glacier, is_debris):
        return {
            'min_elev': self._get_attr(glacier, ['min_elev', 'Zmin'], 4000),
            'max_elev': self._get_attr(glacier, ['max_elev', 'Zmax'], 6000),
            'mean_elev': self._get_attr(glacier, ['mean_elev', 'Zmed'], 5000),
            'area_km2': self._get_attr(glacier, ['area_km2', 'AREA'], 0.1),
            'is_debris': is_debris
        }
    
    def _get_attr(self, row, columns, default):
        for col in columns:
            if hasattr(row, 'index') and col in row.index:
                val = row[col]
                if val is not None and not pd.isna(val):
                    try:
                        return float(val)
                    except:
                        pass
            elif hasattr(row, col):
                val = getattr(row, col)
                if val is not None:
                    try:
                        return float(val)
                    except:
                        pass
        return default
    
    def _create_elevation_bands(self, band_size=100):
        if self.glacier_data is None:
            return
        bands = self._create_bands_from_glaciers(self.glacier_data)
        self.elevation_bands = {
            'centers': bands[0], 'debris_areas': bands[1], 'clean_areas': bands[2]
        }
    
    def _create_bands_from_glaciers(self, glacier_df, band_size=100):
        elev_min = int(glacier_df['min_elev'].min() // 100 * 100)
        elev_max = int(glacier_df['max_elev'].max() // 100 * 100 + 200)
        
        centers = np.arange(elev_min + 50, elev_max, band_size)
        debris_areas = np.zeros(len(centers))
        clean_areas = np.zeros(len(centers))
        
        for _, g in glacier_df.iterrows():
            weights = np.zeros(len(centers))
            for i, c in enumerate(centers):
                if g['min_elev'] <= c <= g['max_elev']:
                    if c <= g['mean_elev']:
                        denom = g['mean_elev'] - g['min_elev']
                        weights[i] = (c - g['min_elev']) / denom if denom > 0 else 0
                    else:
                        denom = g['max_elev'] - g['mean_elev']
                        weights[i] = (g['max_elev'] - c) / denom if denom > 0 else 0
            
            if weights.sum() > 0:
                dist = weights * g['area_km2'] / weights.sum()
                if g['is_debris']:
                    debris_areas += dist
                else:
                    clean_areas += dist
        
        if debris_areas.sum() == 0 and clean_areas.sum() > 0:
            total = clean_areas.copy()
            debris_areas = total * 0.3
            clean_areas = total * 0.7
        
        return centers, debris_areas, clean_areas
    
    def run(self, temp, dates, params=None):
        """Calculate daily glacier melt."""
        if params is None:
            params = self.params
        
        if self.mode == 'yearly' and self.yearly_bands:
            return self._run_yearly(temp, dates, params)
        else:
            return self._run_single(temp, dates, params)
    
    def _run_single(self, temp, dates, params):
        if self.elevation_bands is None:
            raise ValueError("No glacier data loaded")
        
        centers = self.elevation_bands['centers']
        debris_areas = self.elevation_bands['debris_areas']
        clean_areas = self.elevation_bands['clean_areas']
        
        temp_array = np.array(temp).reshape(-1, 1)
        elev_adj = params['lapse_rate'] * (centers - params['ref_elev']) / 1000
        temp_adj = temp_array - elev_adj
        pdd = np.maximum(0, temp_adj - params['t_melt'])
        
        debris_m3 = (pdd * params['ddf_debris'] * debris_areas * 1000).sum(axis=1)
        clean_m3 = (pdd * params['ddf_clean'] * clean_areas * 1000).sum(axis=1)
        
        return {
            'debris_m3s': debris_m3 / SECONDS_PER_DAY,
            'clean_m3s': clean_m3 / SECONDS_PER_DAY,
            'total_m3s': (debris_m3 + clean_m3) / SECONDS_PER_DAY,
            'dates': dates
        }
    
    def _run_yearly(self, temp, dates, params):
        """Run with yearly varying glacier extents."""
        n = len(temp)
        debris_m3s = np.zeros(n)
        clean_m3s = np.zeros(n)
        
        for i, d in enumerate(dates):
            year = d.year
            if year in self.yearly_bands:
                bands = self.yearly_bands[year]
            else:
                # Use nearest year
                available = list(self.yearly_bands.keys())
                year = min(available, key=lambda y: abs(y - d.year))
                bands = self.yearly_bands[year]
            
            centers = bands['centers']
            t = temp[i]
            
            elev_adj = params['lapse_rate'] * (centers - params['ref_elev']) / 1000
            temp_adj = t - elev_adj
            pdd = np.maximum(0, temp_adj - params['t_melt'])
            
            debris_m3s[i] = (pdd * params['ddf_debris'] * bands['debris_areas'] * 1000).sum() / SECONDS_PER_DAY
            clean_m3s[i] = (pdd * params['ddf_clean'] * bands['clean_areas'] * 1000).sum() / SECONDS_PER_DAY
        
        return {
            'debris_m3s': debris_m3s,
            'clean_m3s': clean_m3s,
            'total_m3s': debris_m3s + clean_m3s,
            'dates': dates
        }
    
    def set_params(self, params):
        if isinstance(params, dict):
            self.params.update(params)


# =============================================================================
# HYDROLOGICAL MODEL WITH BASEFLOW PARAMETER
# =============================================================================

class HKPHydroModel:
    """
    HKPM-HM Universal Hydrological Model v1.0
    
    Works for ANY catchment: Alpine glacierized to Lowland rainfall-dominated.
    
    13 Parameters (modular activation based on catchment type):
    
    CORE PARAMETERS (always active - 6):
    - FC: Field capacity (mm) - soil water storage
    - beta: Runoff shape parameter - non-linearity of runoff generation
    - alpha: Quick flow fraction - partitioning between quick and slow flow
    - Kq: Quick flow recession (1/day) - fast response
    - Ks: Slow flow recession (1/day) - baseflow response
    - ETmult: ET correction factor - regional ET calibration
    
    SNOW PARAMETERS (optional for cold catchments - 3):
    - Tt: Temperature threshold (°C) - snow/rain separation
    - Cm: Melt coefficient (mm/°C/day) - degree-day factor
    - lapse_rate: Temperature lapse rate (°C/km) - elevation adjustment
    
    SUBLIMATION PARAMETER (optional for cold arid catchments - 1):
    - Csub: Sublimation coefficient (mm/°C/day) - snow loss in cold arid environments
    
    LOWLAND ENHANCEMENT PARAMETERS (optional - 4):
    - Imax: Interception capacity (mm) - canopy interception (forests)
    - Ki: Interflow recession (1/day) - subsurface lateral flow
    - GWexch: Groundwater exchange (mm/d) - gaining/losing streams
    - LP: ET threshold (-) - fraction of FC for full ET (soil moisture stress)
    """
    
    # ALL PARAMETERS (total including optional sublimation)
    PARAM_NAMES_FULL = [
        'Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ki', 'Ks', 
        'lapse_rate', 'Imax', 'GWexch', 'ETmult', 'LP'
    ]
    
    # Original parameters (for backward compatibility)
    PARAM_NAMES = ['Tt', 'Cm', 'FC', 'beta', 'alpha', 'Kq', 'Ks', 'lapse_rate', 'GWexch']
    
    # Core parameters (no snow) - 6
    PARAM_NAMES_CORE = ['FC', 'beta', 'alpha', 'Kq', 'Ks', 'ETmult']
    
    # Parameter bounds - STANDARD (original)
    PARAM_BOUNDS = [
        (-3.0, 3.0), (1.0, 10.0), (50.0, 600.0), (1.0, 5.0),
        (0.05, 0.95), (0.05, 0.95), (0.001, 0.15), (4.0, 8.0), (-3.0, 3.0)
    ]
    
    # Full parameter bounds - STANDARD (14 params)
    PARAM_BOUNDS_FULL = [
        (-3.0, 3.0),    # Tt - temperature threshold
        (1.0, 10.0),    # Cm - melt coefficient
        (0.0, 0.5),     # Csub - sublimation coefficient
        (50.0, 600.0),  # FC - field capacity
        (1.0, 5.0),     # beta - runoff shape
        (0.05, 0.95),   # alpha - quick flow fraction
        (0.05, 0.95),   # Kq - quick recession
        (0.001, 0.3),   # Ki - interflow recession
        (0.001, 0.15),  # Ks - slow recession
        (4.0, 8.0),     # lapse_rate
        (0.0, 5.0),     # Imax - interception capacity
        (-3.0, 3.0),    # GWexch - groundwater exchange
        (0.5, 1.5),     # ETmult - ET correction
        (0.3, 1.0)      # LP - ET threshold
    ]
    
    # Extended bounds for challenging catchments
    PARAM_BOUNDS_EXTENDED = [
        (-6.0, 6.0),       # Tt - wider for extreme cold environments
        (0.3, 20.0),       # Cm - wider for varying snow/ice conditions
        (10.0, 1500.0),    # FC - wider for varying soil depths
        (0.3, 8.0),        # beta - wider for diverse runoff response
        (0.01, 0.99),      # alpha - nearly full range
        (0.001, 0.999),    # Kq - nearly full range
        (0.0001, 0.5),     # Ks - wider for slow reservoirs
        (2.0, 12.0),       # lapse_rate - wider for complex terrain
        (-5.0, 5.0)        # GWexch - wider for groundwater exchange
    ]
    
    # Full extended bounds (14 params)
    PARAM_BOUNDS_FULL_EXTENDED = [
        (-6.0, 6.0),       # Tt
        (0.3, 20.0),       # Cm
        (0.0, 1.0),        # Csub
        (10.0, 1500.0),    # FC
        (0.3, 8.0),        # beta
        (0.01, 0.99),      # alpha
        (0.001, 0.999),    # Kq
        (0.0001, 0.8),     # Ki
        (0.0001, 0.5),     # Ks
        (2.0, 12.0),       # lapse_rate
        (0.0, 10.0),       # Imax
        (-5.0, 5.0),       # GWexch
        (0.3, 2.0),        # ETmult
        (0.1, 1.0)         # LP
    ]
    
    # Very extended bounds for extreme cases
    PARAM_BOUNDS_VERY_EXTENDED = [
        (-10.0, 10.0),     # Tt
        (0.1, 30.0),       # Cm
        (5.0, 2000.0),     # FC
        (0.1, 10.0),       # beta
        (0.001, 0.999),    # alpha
        (0.0001, 0.9999),  # Kq
        (0.00001, 0.9),    # Ks
        (1.0, 15.0),       # lapse_rate
        (-10.0, 10.0)      # GWexch
    ]
    
    # Full very extended bounds (14 params)
    PARAM_BOUNDS_FULL_VERY_EXTENDED = [
        (-10.0, 10.0),     # Tt
        (0.1, 30.0),       # Cm
        (0.0, 2.0),        # Csub
        (5.0, 2000.0),     # FC
        (0.1, 10.0),       # beta
        (0.001, 0.999),    # alpha
        (0.0001, 0.9999),  # Kq
        (0.00001, 0.9999), # Ki
        (0.00001, 0.9),    # Ks
        (1.0, 15.0),       # lapse_rate
        (0.0, 15.0),       # Imax
        (-10.0, 10.0),     # GWexch
        (0.2, 3.0),        # ETmult
        (0.05, 1.0)        # LP
    ]
    
    PARAM_UNITS = ['°C', 'mm/°C/day', 'mm', '-', '-', '1/day', '1/day', '°C/km', 'mm/d']
    PARAM_UNITS_FULL = ['°C', 'mm/°C/day', 'mm/°C/day', 'mm', '-', '-', '1/day', '1/day', '1/day', 
                        '°C/km', 'mm', 'mm/d', '-', '-']
    
    PARAM_DESC = [
        'Temperature threshold for snow/rain',
        'Degree-day melt coefficient',
        'Field capacity (max soil storage)',
        'Runoff shape parameter',
        'Quick flow fraction',
        'Quick flow recession',
        'Slow flow recession',
        'Temperature lapse rate',
        'Groundwater exchange (+gaining/-losing)'
    ]
    
    PARAM_DESC_FULL = [
        'Temperature threshold for snow/rain',
        'Degree-day melt coefficient',
        'Sublimation coefficient (cold arid snow loss)',
        'Field capacity (max soil storage)',
        'Runoff shape parameter',
        'Quick flow fraction',
        'Quick flow recession',
        'Interflow recession',
        'Slow flow recession',
        'Temperature lapse rate',
        'Interception capacity',
        'Groundwater exchange',
        'ET correction factor',
        'ET soil moisture threshold'
    ]
    
    # Catchment types
    CATCHMENT_TYPES = ['Alpine', 'Lowland', 'Universal']
    
    def __init__(self, area_km2=1000.0, latitude=35.0, catchment_type='Universal'):
        self.area_km2 = area_km2
        self.latitude = latitude
        self.catchment_type = catchment_type  # 'Alpine', 'Lowland', or 'Universal'
        
        # Module switches (can be toggled based on catchment type)
        self.use_snow = True
        self.use_sublimation = False  # Optional: snow loss in cold arid environments
        self.use_interception = True
        self.use_interflow = True
        self.use_gw_exchange = True
        
        # Auto-configure based on catchment type
        self._configure_for_catchment_type()
        
        self.params = self.get_default_params()
        self.elevation_bands = ElevationBands()
        self.calibration_metrics = None
        self.validation_metrics = None
    
    def _configure_for_catchment_type(self):
        """Configure model modules based on catchment type."""
        if self.catchment_type == 'Alpine':
            self.use_snow = True
            self.use_sublimation = True   # Important for cold arid high mountains
            self.use_interception = False  # Less important in high mountains
            self.use_interflow = True
            self.use_gw_exchange = False
        elif self.catchment_type == 'Lowland':
            self.use_snow = False  # Can be enabled if needed
            self.use_sublimation = False  # No snow = no sublimation
            self.use_interception = True  # Important for forests
            self.use_interflow = True
            self.use_gw_exchange = True  # Important for lowlands
        else:  # Universal
            self.use_snow = True
            self.use_sublimation = False  # User can enable if needed
            self.use_interception = True
            self.use_interflow = True
            self.use_gw_exchange = True
    
    def set_catchment_type(self, ctype):
        """Change catchment type and reconfigure."""
        self.catchment_type = ctype
        self._configure_for_catchment_type()
    
    def get_active_param_names(self):
        """Get parameter names based on active modules."""
        params = list(self.PARAM_NAMES_CORE)  # Core always active
        if self.use_snow:
            params = ['Tt', 'Cm'] + params + ['lapse_rate']
        if self.use_sublimation and self.use_snow:
            params.insert(params.index('Cm') + 1, 'Csub')  # After Cm
        if self.use_interception:
            params.append('Imax')
        if self.use_interflow:
            params.append('Ki')
        if self.use_gw_exchange:
            params.append('GWexch')
        params.append('LP')  # Always include LP for ET control
        return params
    
    def _calc_hargreaves_et(self, temp, doy, tmin=None, tmax=None):
        """
        Hargreaves-Samani ET estimation - proper physics-based method.
        Critical for lowland catchments where ET is 50-70% of precipitation!
        
        ET0 = 0.0023 * Ra * (Tmean + 17.8) * sqrt(Tmax - Tmin)
        """
        if temp <= 0:
            return 0.0
        
        # Estimate temperature range if not provided
        if tmin is None or tmax is None:
            # Empirical: diurnal range varies with climate
            delta_t = max(8.0, min(16.0, 10.0 + 0.15 * temp))
        else:
            delta_t = max(tmax - tmin, 1.0)
        
        # Extraterrestrial radiation (Ra) calculation
        lat_rad = np.radians(self.latitude)
        dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
        delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
        
        ws = np.arccos(np.clip(-np.tan(lat_rad) * np.tan(delta), -1, 1))
        
        # Ra in MJ/m²/day
        Ra = (24 * 60 / np.pi) * 0.0820 * dr * (
            ws * np.sin(lat_rad) * np.sin(delta) +
            np.cos(lat_rad) * np.cos(delta) * np.sin(ws)
        )
        
        # Convert to mm/day (1 MJ/m²/day ≈ 0.408 mm/day)
        Ra_mm = Ra * 0.408
        
        # Hargreaves-Samani equation
        ET0 = 0.0023 * Ra_mm * (temp + 17.8) * np.sqrt(max(delta_t, 0.1))
        
        return max(0, ET0)
    
    def set_elevation_bands(self, bands):
        if isinstance(bands, str):
            self.elevation_bands.load_from_file(bands)
        elif isinstance(bands, ElevationBands):
            self.elevation_bands = bands
    
    def _calc_day_length(self, doy):
        lat_rad = np.radians(self.latitude)
        decl = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
        ws = np.arccos(np.clip(-np.tan(lat_rad) * np.tan(decl), -1, 1))
        return 24 * ws / np.pi
    
    def _calc_pet(self, temp, doy, method='hargreaves'):
        """
        Calculate potential evapotranspiration.
        
        Methods:
        - 'hargreaves': Hargreaves-Samani (recommended for data-scarce regions)
        - 'simple': Original simple method (for backward compatibility)
        """
        if temp <= 0:
            return 0.0
        
        if method == 'hargreaves':
            return self._calc_hargreaves_et(temp, doy)
        else:
            # Original simple method (backward compatible)
            dl = self._calc_day_length(doy)
            es = 0.6108 * np.exp(17.27 * temp / (temp + 237.3))
            return max(0, 0.0023 * (dl / 12) * es * (temp + 17.8))
    
    def run(self, precip, temp, dates, glacier_mm=None, params=None, return_components=True):
        """
        Run the Universal Hydrological Model.
        
        Features:
        - Interception module (Imax)
        - Three-pathway routing: Quick + Interflow + Baseflow
        - Groundwater exchange (GWexch)
        - ET with soil moisture stress (LP)
        - ET correction factor (ETmult)
        - Hargreaves-Samani ET estimation
        """
        if params is None:
            params = self.params
        if params is None:
            raise ValueError("No parameters set")
        
        # Extract parameters with defaults for backward compatibility
        if isinstance(params, dict):
            Tt = params.get('Tt', 0.0)
            Cm = params.get('Cm', 5.0)
            Csub = params.get('Csub', 0.0)
            FC = params.get('FC', 200.0)
            beta = params.get('beta', 2.0)
            alpha = params.get('alpha', 0.5)
            Kq = params.get('Kq', 0.1)
            Ki = params.get('Ki', 0.05)  # Interflow
            Ks = params.get('Ks', 0.01)
            lapse_rate = params.get('lapse_rate', DEFAULT_LAPSE_RATE)
            Imax = params.get('Imax', 0.0)  # Interception
            GWexch = params.get('GWexch', 0.0)  # GW exchange
            ETmult = params.get('ETmult', 1.0)  # ET correction
            LP = params.get('LP', 0.7)  # ET threshold
        else:
            # Legacy array format
            Tt, Cm, FC, beta, alpha, Kq, Ks = params[:7]
            lapse_rate = params[7] if len(params) > 7 else DEFAULT_LAPSE_RATE
            GWexch = params[8] if len(params) > 8 else 0.0
            Ki = params[9] if len(params) > 9 else 0.05
            Imax = params[10] if len(params) > 10 else 0.0
            ETmult = params[11] if len(params) > 11 else 1.0
            LP = params[12] if len(params) > 12 else 0.7
        
        n = len(precip)
        precip = np.array(precip)
        temp = np.array(temp)
        
        use_bands = self.elevation_bands.n_bands > 0
        
        if use_bands:
            temp_bands = self.elevation_bands.adjust_temperature(temp, lapse_rate)
            n_bands = self.elevation_bands.n_bands
            area_fracs = self.elevation_bands.bands['area_frac'].values
        else:
            temp_bands = temp.reshape(-1, 1)
            n_bands = 1
            area_fracs = np.array([1.0])
        
        # State variables
        snow = np.zeros((n, n_bands))
        snowmelt_bands = np.zeros((n, n_bands))
        sublimation_bands = np.zeros((n, n_bands))
        rain_bands = np.zeros((n, n_bands))
        snowfall_bands = np.zeros((n, n_bands))
        
        soil = np.zeros(n)
        intercept_store = 0.0  # Interception storage
        Sq, Si, Ss = np.zeros(n), np.zeros(n), np.zeros(n)  # Added Si for interflow
        Qsim = np.zeros(n)
        et = np.zeros(n)
        pet_arr = np.zeros(n)  # Store PET
        runoff = np.zeros(n)
        baseflow = np.zeros(n)
        interflow = np.zeros(n)  # NEW
        quickflow = np.zeros(n)  # NEW
        intercept_evap = np.zeros(n)  # NEW
        throughfall = np.zeros(n)  # NEW
        
        if glacier_mm is None:
            glacier_mm = np.zeros(n)
        else:
            glacier_mm = np.array(glacier_mm)
        
        soil[0] = FC * 0.5
        Tr = 2.0  # Transition temperature range
        
        for t in range(1, n):
            try:
                doy = dates[t].dayofyear
            except:
                doy = t % 365 + 1
            
            P = precip[t]
            
            # =========================================================
            # 1. INTERCEPTION MODULE
            # =========================================================
            if self.use_interception and Imax > 0:
                intercept_store += P
                # Evaporate from interception at potential rate
                T_mean_est = np.average(temp_bands[t], weights=area_fracs)
                pet_int = self._calc_pet(T_mean_est, doy) * ETmult
                evap_int = min(intercept_store, pet_int)
                intercept_store -= evap_int
                intercept_evap[t] = evap_int
                
                # Throughfall
                if intercept_store > Imax:
                    throughfall[t] = intercept_store - Imax
                    intercept_store = Imax
                else:
                    throughfall[t] = 0
                
                P_eff = throughfall[t]
            else:
                P_eff = P
                intercept_evap[t] = 0
                throughfall[t] = P
            
            # =========================================================
            # 2. SNOW MODULE (Original, with option to disable)
            # =========================================================
            total_rain = 0
            total_snowmelt = 0
            
            if self.use_snow:
                for b in range(n_bands):
                    T_band = temp_bands[t, b]
                    
                    # Snow/rain partitioning
                    f_rain = 1.0 / (1.0 + np.exp(-(T_band - Tt) / (Tr / 4.0)))
                    rain_bands[t, b] = P_eff * f_rain
                    snowfall_bands[t, b] = P_eff * (1 - f_rain)
                    
                    snow[t, b] = snow[t-1, b] + snowfall_bands[t, b]
                    
                    # Sublimation: snow loss in cold, arid conditions (T < Tt)
                    if self.use_sublimation and Csub > 0 and T_band < Tt and snow[t, b] > 0:
                        sub_potential = Csub * (Tt - T_band)
                        sublimation_bands[t, b] = min(sub_potential, snow[t, b])
                        snow[t, b] -= sublimation_bands[t, b]
                    
                    # Snowmelt with radiation factor
                    if T_band > Tt and snow[t, b] > 0:
                        f_rad = 1.0 + 0.3 * np.sin(2 * np.pi * (doy - 81) / 365)
                        melt = min(Cm * f_rad * (T_band - Tt), snow[t, b])
                        snowmelt_bands[t, b] = melt
                        snow[t, b] -= melt
                    
                    total_rain += rain_bands[t, b] * area_fracs[b]
                    total_snowmelt += snowmelt_bands[t, b] * area_fracs[b]
            else:
                # No snow module - all precipitation is rain
                total_rain = P_eff
                total_snowmelt = 0
                rain_bands[t, :] = P_eff
            
            T_mean = np.average(temp_bands[t], weights=area_fracs)
            water = total_rain + total_snowmelt + glacier_mm[t]
            
            # =========================================================
            # 3. SOIL MOISTURE & RUNOFF GENERATION
            # =========================================================
            Cr = 1.0 - (1.0 - min(soil[t-1]/FC, 1.0)) ** beta
            runoff[t] = water * Cr
            soil[t] = soil[t-1] + water * (1 - Cr)
            
            # =========================================================
            # 4. EVAPOTRANSPIRATION (Enhanced with LP and ETmult)
            # =========================================================
            pet = self._calc_pet(T_mean, doy) * ETmult
            pet_arr[t] = pet
            
            # Actual ET with soil moisture stress (NEW: LP parameter)
            if soil[t] >= LP * FC:
                # No stress - ET at potential rate
                aet = pet - intercept_evap[t]  # Subtract already evaporated interception
            else:
                # Stress - linear reduction
                aet = (pet - intercept_evap[t]) * (soil[t] / (LP * FC))
            
            aet = max(0, min(aet, soil[t]))  # Can't exceed available water
            et[t] = aet + intercept_evap[t]  # Total ET
            soil[t] -= aet
            
            # Excess soil moisture becomes runoff
            if soil[t] > FC:
                runoff[t] += soil[t] - FC
                soil[t] = FC
            
            # =========================================================
            # 5. THREE-PATHWAY ROUTING (NEW: Quick + Interflow + Baseflow)
            # =========================================================
            # Split runoff into quick and slow components
            quick_in = alpha * runoff[t]
            slow_in = (1 - alpha) * runoff[t]
            
            # Quick flow reservoir
            Sq[t] = Sq[t-1] + quick_in
            Qq = Kq * Sq[t]
            Sq[t] -= Qq
            quickflow[t] = Qq
            
            if self.use_interflow:
                # Split slow flow into interflow and baseflow
                interflow_frac = 0.4  # 40% to interflow, 60% to baseflow
                Si[t] = Si[t-1] + slow_in * interflow_frac
                Qi = Ki * Si[t]
                Si[t] -= Qi
                interflow[t] = Qi
                
                Ss[t] = Ss[t-1] + slow_in * (1 - interflow_frac)
            else:
                # Original two-pathway routing
                Ss[t] = Ss[t-1] + slow_in
                interflow[t] = 0
            
            # Baseflow
            Qs = Ks * Ss[t]
            Ss[t] -= Ks * Ss[t]
            baseflow[t] = Qs
            
            # =========================================================
            # 6. GROUNDWATER EXCHANGE
            # =========================================================
            if self.use_gw_exchange:
                # Positive = gaining stream, Negative = losing stream
                Qs_with_gw = Qs + GWexch
                Qs_with_gw = max(0, Qs_with_gw)  # Can't be negative
            else:
                Qs_with_gw = Qs
            
            # Total discharge
            Qsim[t] = Qq + interflow[t] + Qs_with_gw
        
        # Convert to m³/s
        Qsim_m3s = Qsim * self.area_km2 * 1e6 / (1000 * SECONDS_PER_DAY)
        
        # Aggregate bands
        snow_total = (snow * area_fracs).sum(axis=1)
        snowmelt_total = (snowmelt_bands * area_fracs).sum(axis=1)
        sublimation_total = (sublimation_bands * area_fracs).sum(axis=1)
        rain_total = (rain_bands * area_fracs).sum(axis=1)
        snowfall_total = (snowfall_bands * area_fracs).sum(axis=1)
        
        if return_components:
            return {
                'Q_sim_m3s': Qsim_m3s, 'Q_sim_mm': Qsim,
                'snow': snow_total, 'soil': soil,
                'snowmelt': snowmelt_total, 'sublimation': sublimation_total,
                'rain': rain_total,
                'snowfall': snowfall_total, 'et': et,
                'pet': pet_arr,  # NEW
                'runoff': runoff, 'glacier_melt_mm': glacier_mm,
                'baseflow': baseflow, 
                'quickflow': quickflow,  # NEW
                'interflow': interflow,  # NEW
                'intercept_evap': intercept_evap,  # NEW
                'throughfall': throughfall,  # NEW
                'snow_bands': snow, 'Sq': Sq, 'Si': Si, 'Ss': Ss  # Added Si
            }
        return {'Q_sim_m3s': Qsim_m3s}
    
    def run_with_spinup(self, precip, temp, dates, glacier_mm=None, params=None, 
                        spinup_years=2, return_components=True):
        """
        Run model with automatic spin-up period for proper state initialization.
        
        This is crucial for CSV data where the calibration period starts later
        than the available data. The spin-up runs the model using repeated first-year
        data to initialize snow storage, soil moisture, and reservoir states.
        
        Note: Now properly supports all enhanced features (interception,
        interflow, GW exchange, improved ET) during both spinup and main simulation.
        
        Parameters:
        -----------
        spinup_years : int
            Number of years for spin-up (default: 2)
        """
        if spinup_years > 0 and len(precip) >= 365:
            # Concatenate spinup + actual data and run once
            n_spinup = 365 * spinup_years
            
            # Repeat first year data for spin-up
            spinup_precip = np.tile(precip[:365], spinup_years)
            spinup_temp = np.tile(temp[:365], spinup_years)
            
            if glacier_mm is not None and len(glacier_mm) >= 365:
                spinup_glacier = np.tile(glacier_mm[:365], spinup_years)
            else:
                spinup_glacier = np.zeros(n_spinup)
            
            # Create dates for spinup
            spinup_dates = pd.date_range(end=dates[0] - timedelta(days=1), periods=n_spinup, freq='D')
            
            # Concatenate spinup + actual data
            full_precip = np.concatenate([spinup_precip, np.array(precip)])
            full_temp = np.concatenate([spinup_temp, np.array(temp)])
            full_glacier = np.concatenate([spinup_glacier, np.array(glacier_mm) if glacier_mm is not None else np.zeros(len(precip))])
            full_dates = spinup_dates.append(pd.DatetimeIndex(dates))
            
            # Run entire simulation (spinup + actual)
            full_results = self.run(full_precip, full_temp, full_dates, full_glacier, params, return_components)
            
            # Extract only the actual period results (skip spinup)
            if return_components:
                result = {}
                for key, val in full_results.items():
                    if isinstance(val, np.ndarray):
                        if val.ndim == 1:
                            result[key] = val[n_spinup:]
                        elif val.ndim == 2:
                            result[key] = val[n_spinup:, :]
                    else:
                        result[key] = val
                return result
            else:
                return {'Q_sim_m3s': full_results['Q_sim_m3s'][n_spinup:]}
        else:
            # No spinup, run normally
            return self.run(precip, temp, dates, glacier_mm, params, return_components)
    
    def set_params(self, params):
        if isinstance(params, (list, np.ndarray)):
            # Support both 9-param and 14-param arrays
            if len(params) == 9:
                self.params = dict(zip(self.PARAM_NAMES, params))
            else:
                self.params = dict(zip(self.PARAM_NAMES_FULL[:len(params)], params))
        else:
            self.params = params.copy() if isinstance(params, dict) else params
    
    def get_default_params(self, full=True):
        """Get default parameters.
        
        Args:
            full: If True, return all parameters. If False, return original 9.
        """
        if full:
            return {
                'Tt': 0.0, 'Cm': 5.0, 'Csub': 0.0, 'FC': 200.0, 'beta': 2.0,
                'alpha': 0.5, 'Kq': 0.1, 'Ki': 0.05, 'Ks': 0.01,
                'lapse_rate': 6.5,
                'Imax': 2.0, 'GWexch': 0.0, 'ETmult': 1.0, 'LP': 0.7
            }
        else:
            return {name: (b[0] + b[1]) / 2 for name, b in zip(self.PARAM_NAMES, self.PARAM_BOUNDS)}
    
    def save(self, filepath):
        with open(filepath, 'wb') as f:
            pickle.dump(self, f)
    
    @staticmethod
    def load(filepath):
        with open(filepath, 'rb') as f:
            return pickle.load(f)


# =============================================================================
# PERFORMANCE METRICS
# =============================================================================

def calc_nse(obs, sim):
    mask = ~(np.isnan(obs) | np.isnan(sim))
    if mask.sum() < 2: return -999
    obs, sim = obs[mask], sim[mask]
    ss_res = np.sum((obs - sim)**2)
    ss_tot = np.sum((obs - np.mean(obs))**2)
    return 1 - ss_res/ss_tot if ss_tot > 0 else -999

def calc_nse_log(obs, sim):
    mask = ~(np.isnan(obs) | np.isnan(sim)) & (obs > 0) & (sim > 0)
    if mask.sum() < 2: return -999
    return calc_nse(np.log(obs[mask]), np.log(sim[mask]))

def calc_kge(obs, sim):
    mask = ~(np.isnan(obs) | np.isnan(sim))
    if mask.sum() < 2: return -999
    obs, sim = obs[mask], sim[mask]
    r = np.corrcoef(obs, sim)[0, 1]
    alpha = np.std(sim) / (np.std(obs) + 1e-10)
    beta = np.mean(sim) / (np.mean(obs) + 1e-10)
    return 1 - np.sqrt((r-1)**2 + (alpha-1)**2 + (beta-1)**2)

def calc_pbias(obs, sim):
    mask = ~(np.isnan(obs) | np.isnan(sim))
    if mask.sum() < 2: return 999
    obs, sim = obs[mask], sim[mask]
    return 100 * np.sum(sim - obs) / np.sum(obs) if np.sum(obs) > 0 else 999

def calc_rmse(obs, sim):
    mask = ~(np.isnan(obs) | np.isnan(sim))
    if mask.sum() < 2: return 999
    return np.sqrt(np.mean((obs[mask] - sim[mask])**2))

def calc_all_metrics(obs, sim, warmup=0):
    obs, sim = np.array(obs)[warmup:], np.array(sim)[warmup:]
    return {
        'NSE': calc_nse(obs, sim), 'NSE_log': calc_nse_log(obs, sim),
        'KGE': calc_kge(obs, sim), 'PBIAS': calc_pbias(obs, sim), 'RMSE': calc_rmse(obs, sim)
    }


# =============================================================================
# ADVANCED OPTIMIZATION ALGORITHMS
# =============================================================================

class ParticleSwarmOptimizer:
    """Particle Swarm Optimization (PSO) for robust global optimization."""
    
    def __init__(self, objective, bounds, n_particles=30, max_iter=100, 
                 w=0.7, c1=1.5, c2=1.5, seed=None):
        self.objective = objective
        self.bounds = np.array(bounds)
        self.n_particles = n_particles
        self.max_iter = max_iter
        self.w = w    # Inertia weight
        self.c1 = c1  # Cognitive component
        self.c2 = c2  # Social component
        self.dim = len(bounds)
        
        if seed is not None:
            np.random.seed(seed)
        
        self.positions = np.random.uniform(
            self.bounds[:, 0], self.bounds[:, 1], (n_particles, self.dim))
        self.velocities = np.zeros((n_particles, self.dim))
        
        self.pbest = self.positions.copy()
        self.pbest_scores = np.full(n_particles, np.inf)
        self.gbest = self.positions[0].copy()
        self.gbest_score = np.inf
    
    def optimize(self, callback=None):
        for iteration in range(self.max_iter):
            for i in range(self.n_particles):
                try:
                    score = self.objective(self.positions[i])
                except (StopIteration, SystemExit):
                    raise
                except:
                    score = 1e10
                
                if score < self.pbest_scores[i]:
                    self.pbest[i] = self.positions[i].copy()
                    self.pbest_scores[i] = score
                
                if score < self.gbest_score:
                    self.gbest = self.positions[i].copy()
                    self.gbest_score = score
            
            for i in range(self.n_particles):
                r1, r2 = np.random.rand(self.dim), np.random.rand(self.dim)
                cognitive = self.c1 * r1 * (self.pbest[i] - self.positions[i])
                social = self.c2 * r2 * (self.gbest - self.positions[i])
                self.velocities[i] = self.w * self.velocities[i] + cognitive + social
                self.positions[i] = np.clip(self.positions[i] + self.velocities[i], 
                                           self.bounds[:, 0], self.bounds[:, 1])
            
            if callback:
                callback(iteration, self.gbest, self.gbest_score)
        
        return {'x': self.gbest, 'fun': self.gbest_score}


class ShuffledComplexEvolution:
    """SCE-UA algorithm - very effective for hydrological model calibration."""
    
    def __init__(self, objective, bounds, n_complexes=4, points_per_complex=None,
                 max_iter=1000, seed=None):
        self.objective = objective
        self.bounds = np.array(bounds)
        self.dim = len(bounds)
        self.n_complexes = n_complexes
        
        if points_per_complex is None:
            points_per_complex = 2 * self.dim + 1
        self.points_per_complex = points_per_complex
        self.n_points = n_complexes * points_per_complex
        self.max_iter = max_iter
        
        if seed is not None:
            np.random.seed(seed)
        
        # Initialize with Latin Hypercube if available
        try:
            sampler = qmc.LatinHypercube(d=self.dim, seed=seed)
            sample = sampler.random(n=self.n_points)
            self.population = qmc.scale(sample, self.bounds[:, 0], self.bounds[:, 1])
        except:
            self.population = np.random.uniform(
                self.bounds[:, 0], self.bounds[:, 1], (self.n_points, self.dim))
        
        self.scores = np.full(self.n_points, np.inf)
        self.best = None
        self.best_score = np.inf
    
    def _evaluate_population(self):
        for i in range(self.n_points):
            try:
                self.scores[i] = self.objective(self.population[i])
            except (StopIteration, SystemExit):
                raise
            except:
                self.scores[i] = 1e10
            
            if self.scores[i] < self.best_score:
                self.best_score = self.scores[i]
                self.best = self.population[i].copy()
    
    def _evolve_complex(self, complex_indices, n_evolutions=None):
        if n_evolutions is None:
            n_evolutions = self.points_per_complex
        
        for _ in range(n_evolutions):
            n_subcomplex = min(self.dim + 1, len(complex_indices))
            probs = 2 * (len(complex_indices) - np.arange(len(complex_indices))) / \
                   (len(complex_indices) * (len(complex_indices) + 1))
            probs /= probs.sum()
            
            sub_idx = np.random.choice(len(complex_indices), n_subcomplex, 
                                       replace=False, p=probs)
            sub_points = complex_indices[sub_idx]
            
            worst_idx = sub_points[np.argmax(self.scores[sub_points])]
            centroid = np.mean(self.population[sub_points[:-1]], axis=0)
            
            # Reflection
            new_point = 2 * centroid - self.population[worst_idx]
            new_point = np.clip(new_point, self.bounds[:, 0], self.bounds[:, 1])
            
            try:
                new_score = self.objective(new_point)
            except (StopIteration, SystemExit):
                raise
            except:
                new_score = 1e10
            
            if new_score < self.scores[worst_idx]:
                self.population[worst_idx] = new_point
                self.scores[worst_idx] = new_score
            else:
                # Contraction
                new_point = (centroid + self.population[worst_idx]) / 2
                new_point = np.clip(new_point, self.bounds[:, 0], self.bounds[:, 1])
                
                try:
                    new_score = self.objective(new_point)
                except (StopIteration, SystemExit):
                    raise
                except:
                    new_score = 1e10
                
                if new_score < self.scores[worst_idx]:
                    self.population[worst_idx] = new_point
                    self.scores[worst_idx] = new_score
                else:
                    # Random point
                    new_point = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
                    try:
                        new_score = self.objective(new_point)
                    except (StopIteration, SystemExit):
                        raise
                    except:
                        new_score = 1e10
                    self.population[worst_idx] = new_point
                    self.scores[worst_idx] = new_score
            
            if self.scores[worst_idx] < self.best_score:
                self.best_score = self.scores[worst_idx]
                self.best = self.population[worst_idx].copy()
    
    def optimize(self, callback=None):
        self._evaluate_population()
        
        for iteration in range(self.max_iter):
            sort_idx = np.argsort(self.scores)
            self.population = self.population[sort_idx]
            self.scores = self.scores[sort_idx]
            
            complexes = []
            for i in range(self.n_complexes):
                complex_idx = np.arange(i, self.n_points, self.n_complexes)
                complexes.append(complex_idx)
            
            for c_idx in complexes:
                self._evolve_complex(c_idx)
            
            if callback:
                callback(iteration, self.best, self.best_score)
        
        return {'x': self.best, 'fun': self.best_score}


class AdaptiveDifferentialEvolution:
    """Adaptive DE with self-adapting control parameters."""
    
    def __init__(self, objective, bounds, popsize=20, max_iter=100, 
                 F_init=0.5, CR_init=0.9, seed=None):
        self.objective = objective
        self.bounds = np.array(bounds)
        self.dim = len(bounds)
        self.popsize = popsize
        self.max_iter = max_iter
        
        if seed is not None:
            np.random.seed(seed)
        
        self.population = np.random.uniform(
            self.bounds[:, 0], self.bounds[:, 1], (popsize, self.dim))
        self.F = np.full(popsize, F_init)
        self.CR = np.full(popsize, CR_init)
        self.scores = np.full(popsize, np.inf)
        self.best = None
        self.best_score = np.inf
    
    def _mutate(self, target_idx):
        idxs = [i for i in range(self.popsize) if i != target_idx]
        r1, r2, r3 = np.random.choice(idxs, 3, replace=False)
        mutant = self.population[r1] + self.F[target_idx] * (self.population[r2] - self.population[r3])
        return np.clip(mutant, self.bounds[:, 0], self.bounds[:, 1])
    
    def _crossover(self, target, mutant, target_idx):
        trial = target.copy()
        j_rand = np.random.randint(self.dim)
        for j in range(self.dim):
            if np.random.rand() < self.CR[target_idx] or j == j_rand:
                trial[j] = mutant[j]
        return trial
    
    def _adapt_parameters(self, target_idx, success):
        if success:
            self.F[target_idx] = min(1.0, self.F[target_idx] + 0.1 * np.random.rand())
            self.CR[target_idx] = min(1.0, self.CR[target_idx] + 0.1 * np.random.rand())
        else:
            self.F[target_idx] = max(0.1, self.F[target_idx] - 0.05 * np.random.rand())
            self.CR[target_idx] = max(0.1, self.CR[target_idx] - 0.05 * np.random.rand())
    
    def optimize(self, callback=None):
        for i in range(self.popsize):
            try:
                self.scores[i] = self.objective(self.population[i])
            except (StopIteration, SystemExit):
                raise
            except:
                self.scores[i] = 1e10
            if self.scores[i] < self.best_score:
                self.best_score = self.scores[i]
                self.best = self.population[i].copy()
        
        for iteration in range(self.max_iter):
            for i in range(self.popsize):
                mutant = self._mutate(i)
                trial = self._crossover(self.population[i], mutant, i)
                
                try:
                    trial_score = self.objective(trial)
                except (StopIteration, SystemExit):
                    raise
                except:
                    trial_score = 1e10
                
                if trial_score <= self.scores[i]:
                    self.population[i] = trial
                    self.scores[i] = trial_score
                    self._adapt_parameters(i, True)
                    if trial_score < self.best_score:
                        self.best_score = trial_score
                        self.best = trial.copy()
                else:
                    self._adapt_parameters(i, False)
            
            if callback:
                callback(iteration, self.best, self.best_score)
        
        return {'x': self.best, 'fun': self.best_score}


# =============================================================================
# GUI APPLICATION
# =============================================================================

class HKPHM_GUI:
    """Main GUI Application."""
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1700x1050")
        
        # Data storage
        self.temp_data = None
        self.precip_data = None
        self.obs_flow_calib = None
        self.obs_flow_valid = None
        self.swe_obs_data = None
        self.glacier_melt_input = None
        
        # Ungauged data
        self.ungauged_temp = None
        self.ungauged_precip = None
        self.ungauged_glacier = None
        self.ungauged_obs = None
        self.ungauged_elev_bands = None
        
        # Models
        self.hydro_model = None
        self.glacier_model = None
        self.elevation_bands = ElevationBands()
        
        # Results
        self.results_calib = None
        self.results_valid = None
        self.results_proj = None
        self.results_ungauged = None
        self.glacier_results = None
        self.sensitivity_results = None
        
        # Optimization control
        self.optimization_running = False
        self.optimization_stop = False
        self.iteration_history = []  # Store ALL iterations
        self.best_results = []  # Store top 3 results
        self.stored_optimized_params = None  # Preserved copy from optimization (never overwritten by manual runs)
        
        self.create_menu()
        self.create_widgets()
        self.log_startup()
    
    def log_startup(self):
        self.log(f"{APP_NAME}")
        self.log(f"Version: {APP_VERSION}")
        self.log(f"Author: {AUTHOR}")
        self.log(f"GitHub: {GITHUB_URL}")
        self.log("-" * 50)
        self.log("  - Works for ANY catchment (Alpine to Lowland)")
        self.log("  - Hargreaves-Samani ET estimation")
        self.log("  - Interception module (Imax)")
        self.log("  - Three-pathway routing (Quick+Inter+Base)")
        self.log("  - Groundwater exchange (GWexch)")
        self.log("  - ET correction factor (ETmult)")
        self.log("  - 14 parameters (5 NEW for lowlands)")
        self.log("-" * 50)
        self.log("Ready. Select catchment type and load data.")
    
    def create_menu(self):
        menubar = tk.Menu(self.root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Temperature", command=self.load_temperature)
        file_menu.add_command(label="Load Precipitation", command=self.load_precipitation)
        file_menu.add_command(label="Load Calibration Flow", command=self.load_calib_flow)
        file_menu.add_command(label="Load Validation Flow", command=self.load_valid_flow)
        file_menu.add_command(label="Load Catchment Shapefile", command=self.load_catchment_shp)
        file_menu.add_separator()
        file_menu.add_command(label="Load Elevation Bands", command=self.load_elev_bands)
        file_menu.add_separator()
        file_menu.add_command(label="Save Model", command=self.save_model_pkl)
        file_menu.add_command(label="Load Model", command=self.load_saved_model)
        file_menu.add_separator()
        file_menu.add_command(label="Save All Results", command=self.save_all_results)
        file_menu.add_command(label="⚡ Quick Save All (Smart Path)", command=self.quick_save_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Export menu
        export_menu = tk.Menu(menubar, tearoff=0)
        export_menu.add_command(label="Export Iteration History", command=self.export_iteration_history)
        export_menu.add_command(label="Export Projection Results", command=self.export_projection_results)
        export_menu.add_command(label="Export Glacier Results", command=self.export_glacier_results)
        export_menu.add_command(label="Export Glacier Post-Cal Results", command=self.export_glacier_postcal_results)
        export_menu.add_command(label="Export Ungauged Results", command=self.export_ungauged_results)
        export_menu.add_command(label="Export Sensitivity Results", command=self.export_sensitivity_results)
        menubar.add_cascade(label="Export", menu=export_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="User Guide", command=self.show_user_guide)
        help_menu.add_command(label="GitHub", command=lambda: webbrowser.open(GITHUB_URL))
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_widgets(self):
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(main_pane, width=520)
        main_pane.add(left_frame, weight=1)
        
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=3)
        
        self.create_left_panel(left_frame)
        self.create_right_panel(right_frame)
    
    def create_left_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        tabs = [
            ("Data", self.create_data_tab),
            ("Elev. Bands", self.create_elev_bands_tab),
            ("Periods", self.create_periods_tab),
            ("Calibration", self.create_calibration_tab),
            ("Optimization", self.create_optimization_tab),
            ("Glacier", self.create_glacier_tab),
            ("Glacier Post-Cal", self.create_glacier_postcal_tab),
            ("Ungauged", self.create_ungauged_tab),
            ("Sensitivity", self.create_sens_tab)
        ]
        
        for name, creator in tabs:
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=name)
            creator(tab)
    
    def create_data_tab(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Catchment Type Selector (Universal)
        type_frame = ttk.LabelFrame(scrollable, text="Catchment Type")
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.catchment_type_var = tk.StringVar(value="Universal")
        types_info = [
            ("Alpine", "Mountains, glaciers, snow-dominated"),
            ("Lowland", "Rainfall-dominated, forests, GW influence"),
            ("Universal", "All processes active (recommended)")
        ]
        for ctype, desc in types_info:
            ttk.Radiobutton(type_frame, text=f"{ctype}: {desc}", 
                           variable=self.catchment_type_var, value=ctype,
                           command=self.on_catchment_type_change).pack(anchor='w', padx=5)
        
        # Module switches
        modules_frame = ttk.LabelFrame(scrollable, text="Active Modules")
        modules_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.use_snow_var = tk.BooleanVar(value=True)
        self.use_sublimation_var = tk.BooleanVar(value=False)
        self.use_intercept_var = tk.BooleanVar(value=True)
        self.use_interflow_var = tk.BooleanVar(value=True)
        self.use_gw_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(modules_frame, text="Snow module (cold regions)", 
                       variable=self.use_snow_var).pack(anchor='w', padx=5)
        ttk.Checkbutton(modules_frame, text="Sublimation (cold arid snow loss)", 
                       variable=self.use_sublimation_var).pack(anchor='w', padx=5)
        ttk.Checkbutton(modules_frame, text="Interception (forests)", 
                       variable=self.use_intercept_var).pack(anchor='w', padx=5)
        ttk.Checkbutton(modules_frame, text="Interflow (3-pathway routing)", 
                       variable=self.use_interflow_var).pack(anchor='w', padx=5)
        ttk.Checkbutton(modules_frame, text="Groundwater exchange", 
                       variable=self.use_gw_var).pack(anchor='w', padx=5)
        
        ttk.Button(modules_frame, text="Auto-Detect from Data", 
                  command=self.auto_detect_modules).pack(fill=tk.X, padx=5, pady=3)
        
        info_frame = ttk.LabelFrame(scrollable, text="Catchment Information")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.entry_vars = {}
        fields = [("Name:", "catchment_name", ""), ("Area (km²):", "area", "1000"),
                  ("Latitude (°):", "lat", "35.0"), ("Longitude (°):", "lon", "70.0")]
        
        for i, (label, key, default) in enumerate(fields):
            ttk.Label(info_frame, text=label).grid(row=i, column=0, sticky='w', padx=5, pady=2)
            var = tk.StringVar(value=default)
            self.entry_vars[key] = var
            ttk.Entry(info_frame, textvariable=var, width=20).grid(row=i, column=1, padx=5, pady=2)
        
        ttk.Button(info_frame, text="Load from Shapefile", command=self.load_catchment_shp).grid(
            row=len(fields), column=0, columnspan=2, pady=5)
        
        # ── Auto-Load from Folder Structure ──
        auto_frame = ttk.LabelFrame(scrollable, text="Auto-Load from Folder Structure")
        auto_frame.pack(fill=tk.X, padx=5, pady=5)
        
        path_row = ttk.Frame(auto_frame)
        path_row.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(path_row, text="Base Path:").pack(side=tk.LEFT)
        self.base_path_var = tk.StringVar(value=r"E:\Project3\Catchments")
        ttk.Entry(path_row, textvariable=self.base_path_var, width=35).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse", command=self._browse_base_path).pack(side=tk.LEFT, padx=2)
        
        name_row = ttk.Frame(auto_frame)
        name_row.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(name_row, text="Catchment:").pack(side=tk.LEFT)
        self.auto_catchment_var = tk.StringVar(value="")
        ttk.Entry(name_row, textvariable=self.auto_catchment_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(name_row, text="Auto-Load", command=self.auto_load_catchment_data).pack(side=tk.LEFT, padx=5)
        
        self.auto_load_status = ttk.Label(auto_frame, text="Enter catchment folder name and click Auto-Load", foreground='gray')
        self.auto_load_status.pack(anchor='w', padx=5, pady=3)
        
        # Flow upload mode
        flow_mode_frame = ttk.LabelFrame(scrollable, text="Flow Data Mode")
        flow_mode_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.flow_mode_var = tk.StringVar(value="separate")
        ttk.Radiobutton(flow_mode_frame, text="Separate files (Calib + Valid)", 
                       variable=self.flow_mode_var, value="separate").pack(anchor='w', padx=5)
        ttk.Radiobutton(flow_mode_frame, text="Single file (auto-split by period)", 
                       variable=self.flow_mode_var, value="single").pack(anchor='w', padx=5)
        
        single_frame = ttk.Frame(flow_mode_frame)
        single_frame.pack(fill=tk.X, padx=5, pady=3)
        ttk.Button(single_frame, text="Load Single Flow File", 
                  command=self.load_single_flow_file).pack(side=tk.LEFT, padx=3)
        self.single_flow_status = ttk.Label(single_frame, text="", foreground='gray')
        self.single_flow_status.pack(side=tk.LEFT, padx=5)
        
        files_frame = ttk.LabelFrame(scrollable, text="Input Data")
        files_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_labels = {}
        buttons = [
            ("Temperature", self.load_temperature, "temp"),
            ("Precipitation", self.load_precipitation, "precip"),
            ("Calib. Flow", self.load_calib_flow, "flow_cal"),
            ("Valid. Flow", self.load_valid_flow, "flow_val"),
            ("Glacier Melt", self.load_glacier_melt_csv, "glacier_melt"),
            ("SWE Observed (optional)", self.load_swe_observed, "swe_obs")
        ]
        
        for i, (text, cmd, key) in enumerate(buttons):
            ttk.Button(files_frame, text=f"Load {text}", command=cmd, width=16).grid(row=i, column=0, padx=5, pady=2)
            lbl = ttk.Label(files_frame, text="○ Not loaded", foreground='gray')
            lbl.grid(row=i, column=1, padx=5, pady=2, sticky='w')
            self.status_labels[key] = lbl
        
        log_frame = ttk.LabelFrame(scrollable, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = ScrolledText(log_frame, height=12, width=50, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def on_catchment_type_change(self):
        """Handle catchment type selection change."""
        ctype = self.catchment_type_var.get()
        
        if ctype == 'Alpine':
            self.use_snow_var.set(True)
            self.use_sublimation_var.set(True)
            self.use_intercept_var.set(False)
            self.use_interflow_var.set(True)
            self.use_gw_var.set(False)
        elif ctype == 'Lowland':
            self.use_snow_var.set(False)
            self.use_sublimation_var.set(False)
            self.use_intercept_var.set(True)
            self.use_interflow_var.set(True)
            self.use_gw_var.set(True)
        else:  # Universal
            self.use_snow_var.set(True)
            self.use_sublimation_var.set(False)
            self.use_intercept_var.set(True)
            self.use_interflow_var.set(True)
            self.use_gw_var.set(True)
        
        self.log(f"Catchment type set to: {ctype}")
        self.update_parameter_display()
    
    def auto_detect_modules(self):
        """Auto-detect which modules are needed based on data."""
        if self.temp_data is None:
            messagebox.showwarning("Warning", "Load temperature data first")
            return
        
        min_temp = self.temp_data.min()
        mean_temp = self.temp_data.mean()
        
        # Detect snow need
        if min_temp < 2.0:
            self.use_snow_var.set(True)
            self.log(f"Snow module: ON (min temp = {min_temp:.1f}°C)")
            # Detect sublimation need: cold + arid high-altitude environments
            if min_temp < -5.0 and mean_temp < 10.0:
                self.use_sublimation_var.set(True)
                self.log(f"Sublimation: ON (cold arid conditions, mean temp = {mean_temp:.1f}°C)")
            else:
                self.use_sublimation_var.set(False)
                self.log(f"Sublimation: OFF (not cold/arid enough)")
        else:
            self.use_snow_var.set(False)
            self.use_sublimation_var.set(False)
            self.log(f"Snow module: OFF (min temp = {min_temp:.1f}°C, no snow expected)")
        
        # Suggest catchment type
        if min_temp < -10:
            self.catchment_type_var.set('Alpine')
            self.log("Detected: Alpine catchment (cold climate)")
        elif min_temp > 5:
            self.catchment_type_var.set('Lowland')
            self.log("Detected: Lowland catchment (warm climate)")
        else:
            self.catchment_type_var.set('Universal')
            self.log("Detected: Mixed climate - using Universal mode")
        
        self.update_parameter_display()
    
    def update_parameter_display(self):
        """Update parameter display based on active modules."""
        # This can be called to refresh parameter panels when modules change
        pass
    
    def create_elev_bands_tab(self, parent):
        load_frame = ttk.LabelFrame(parent, text="Load Elevation Bands")
        load_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(load_frame, text="Load from File (CSV/Excel)", 
                  command=self.load_elev_bands).pack(fill=tk.X, padx=5, pady=5)
        
        self.elev_bands_status = ttk.Label(load_frame, text="○ Not loaded (lumped)", foreground='gray')
        self.elev_bands_status.pack(anchor='w', padx=5, pady=2)
        
        manual_frame = ttk.LabelFrame(parent, text="Manual Entry")
        manual_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(manual_frame, text="Format: Elevation(m), Area(km²)").pack(anchor='w', padx=5)
        
        self.elev_bands_text = ScrolledText(manual_frame, height=6, width=40, font=('Consolas', 9))
        self.elev_bands_text.pack(fill=tk.X, padx=5, pady=5)
        
        btn_frame = ttk.Frame(manual_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Apply", command=self.apply_manual_elev_bands).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Clear", command=self.clear_elev_bands).pack(side=tk.LEFT, padx=3)
        
        display_frame = ttk.LabelFrame(parent, text="Current Bands")
        display_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.elev_bands_display = ScrolledText(display_frame, height=8, width=40, font=('Consolas', 9))
        self.elev_bands_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.elev_bands_display.insert('1.0', "No elevation bands")
        self.elev_bands_display.config(state=tk.DISABLED)
    
    def create_periods_tab(self, parent):
        calib_frame = ttk.LabelFrame(parent, text="Calibration Period")
        calib_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(calib_frame, text="Start:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.calib_start_var = tk.StringVar(value="2007-01-01")
        ttk.Entry(calib_frame, textvariable=self.calib_start_var, width=12).grid(row=0, column=1, padx=5)
        
        ttk.Label(calib_frame, text="End:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.calib_end_var = tk.StringVar(value="2015-12-31")
        ttk.Entry(calib_frame, textvariable=self.calib_end_var, width=12).grid(row=1, column=1, padx=5)
        
        valid_frame = ttk.LabelFrame(parent, text="Validation Period")
        valid_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(valid_frame, text="Start:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.valid_start_var = tk.StringVar(value="2016-01-01")
        ttk.Entry(valid_frame, textvariable=self.valid_start_var, width=12).grid(row=0, column=1, padx=5)
        
        ttk.Label(valid_frame, text="End:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.valid_end_var = tk.StringVar(value="2021-12-31")
        ttk.Entry(valid_frame, textvariable=self.valid_end_var, width=12).grid(row=1, column=1, padx=5)
        
        proj_frame = ttk.LabelFrame(parent, text="Projection Period")
        proj_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(proj_frame, text="Start:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.proj_start_var = tk.StringVar(value="2022-01-01")
        ttk.Entry(proj_frame, textvariable=self.proj_start_var, width=12).grid(row=0, column=1, padx=5)
        
        ttk.Label(proj_frame, text="End:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.proj_end_var = tk.StringVar(value="2030-12-31")
        ttk.Entry(proj_frame, textvariable=self.proj_end_var, width=12).grid(row=1, column=1, padx=5)
        
        set_frame = ttk.LabelFrame(parent, text="Settings")
        set_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(set_frame, text="Warmup (days):").grid(row=0, column=0, sticky='w', padx=5)
        self.warmup_var = tk.StringVar(value="30")
        ttk.Entry(set_frame, textvariable=self.warmup_var, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(set_frame, text="Spinup (years):").grid(row=0, column=2, sticky='w', padx=5)
        self.spinup_var = tk.StringVar(value="2")
        ttk.Entry(set_frame, textvariable=self.spinup_var, width=4).grid(row=0, column=3, padx=5)
    
    def create_calibration_tab(self, parent):
        """Manual Calibration Tab with entry boxes for specific values"""
        
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        info_frame = ttk.Frame(scrollable)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="Manual Calibration - HKPM-HM Universal", 
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        
        # Glacier option
        glacier_frame = ttk.LabelFrame(scrollable, text="Glacier Option")
        glacier_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.glacier_opt_var = tk.StringVar(value="none")
        ttk.Radiobutton(glacier_frame, text="None", variable=self.glacier_opt_var, value="none").pack(anchor='w', padx=5)
        ttk.Radiobutton(glacier_frame, text="External Data", variable=self.glacier_opt_var, value="external").pack(anchor='w', padx=5)
        ttk.Radiobutton(glacier_frame, text="Integrated Model", variable=self.glacier_opt_var, value="integrated").pack(anchor='w', padx=5)
        
        self.glacier_calib_var = tk.StringVar(value="with")
        ttk.Radiobutton(glacier_frame, text="Calibrate WITH glacier", variable=self.glacier_calib_var, value="with").pack(anchor='w', padx=5)
        ttk.Radiobutton(glacier_frame, text="Calibrate WITHOUT glacier (add after)", variable=self.glacier_calib_var, value="without").pack(anchor='w', padx=5)
        
        # Bounds selection
        bounds_frame = ttk.LabelFrame(scrollable, text="Parameter Bounds")
        bounds_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.bounds_selection_var = tk.StringVar(value="Standard")
        ttk.Radiobutton(bounds_frame, text="Standard", variable=self.bounds_selection_var, 
                       value="Standard", command=self.update_slider_bounds).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(bounds_frame, text="Extended", variable=self.bounds_selection_var, 
                       value="Extended", command=self.update_slider_bounds).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(bounds_frame, text="Very Extended", variable=self.bounds_selection_var, 
                       value="VeryExtended", command=self.update_slider_bounds).pack(side=tk.LEFT, padx=5)
        
        # Extended bounds checkbox (legacy)
        self.ext_bounds_var = tk.BooleanVar(value=False)
        
        # CORE Parameters (always active)
        core_frame = ttk.LabelFrame(scrollable, text="CORE Parameters (6)")
        core_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.param_vars = {}
        self.param_sliders = {}
        self.param_entries = {}
        
        core_params = [
            ('FC', (50.0, 600.0), 'mm', 'Field capacity'),
            ('beta', (1.0, 5.0), '-', 'Runoff shape'),
            ('alpha', (0.05, 0.95), '-', 'Quick flow fraction'),
            ('Kq', (0.05, 0.95), '1/d', 'Quick recession'),
            ('Ks', (0.001, 0.15), '1/d', 'Slow recession'),
                        ('ETmult', (0.5, 1.5), '-', 'ET correction')
        ]
        
        for i, (name, bounds, unit, desc) in enumerate(core_params):
            ttk.Label(core_frame, text=f"{name} ({unit})").grid(row=i, column=0, sticky='w', padx=2)
            
            default = (bounds[0] + bounds[1]) / 2
            var = tk.DoubleVar(value=default)
            self.param_vars[name] = var
            
            slider = ttk.Scale(core_frame, from_=bounds[0], to=bounds[1], variable=var,
                              orient=tk.HORIZONTAL, length=100,
                              command=lambda v, n=name: self.on_slider_change(n))
            slider.grid(row=i, column=1, padx=2)
            self.param_sliders[name] = slider
            
            entry_var = tk.StringVar(value=f"{default:.4f}")
            entry = ttk.Entry(core_frame, textvariable=entry_var, width=8)
            entry.grid(row=i, column=2, padx=2)
            entry.bind('<Return>', lambda e, n=name: self.on_entry_change(n))
            entry.bind('<FocusOut>', lambda e, n=name: self.on_entry_change(n))
            self.param_entries[name] = entry_var
        
        # SNOW Parameters
        snow_frame = ttk.LabelFrame(scrollable, text="SNOW Parameters (4) - Optional")
        snow_frame.pack(fill=tk.X, padx=5, pady=5)
        
        snow_params = [
            ('Tt', (-3.0, 3.0), '°C', 'Temperature threshold'),
            ('Cm', (1.0, 10.0), 'mm/°C/d', 'Melt coefficient'),
            ('Csub', (0.0, 0.5), 'mm/°C/d', 'Sublimation coeff.'),
            ('lapse_rate', (4.0, 8.0), '°C/km', 'Lapse rate')
        ]
        
        for i, (name, bounds, unit, desc) in enumerate(snow_params):
            ttk.Label(snow_frame, text=f"{name} ({unit})").grid(row=i, column=0, sticky='w', padx=2)
            
            default = (bounds[0] + bounds[1]) / 2
            var = tk.DoubleVar(value=default)
            self.param_vars[name] = var
            
            slider = ttk.Scale(snow_frame, from_=bounds[0], to=bounds[1], variable=var,
                              orient=tk.HORIZONTAL, length=100,
                              command=lambda v, n=name: self.on_slider_change(n))
            slider.grid(row=i, column=1, padx=2)
            self.param_sliders[name] = slider
            
            entry_var = tk.StringVar(value=f"{default:.4f}")
            entry = ttk.Entry(snow_frame, textvariable=entry_var, width=8)
            entry.grid(row=i, column=2, padx=2)
            entry.bind('<Return>', lambda e, n=name: self.on_entry_change(n))
            entry.bind('<FocusOut>', lambda e, n=name: self.on_entry_change(n))
            self.param_entries[name] = entry_var
        
        # LOWLAND Enhancement Parameters
        lowland_frame = ttk.LabelFrame(scrollable, text="LOWLAND Parameters (4)")
        lowland_frame.pack(fill=tk.X, padx=5, pady=5)
        
        lowland_params = [
            ('Imax', (0.0, 5.0), 'mm', 'Interception capacity'),
            ('Ki', (0.001, 0.3), '1/d', 'Interflow recession'),
            ('GWexch', (-3.0, 3.0), 'mm/d', 'GW exchange (+gain/-lose)'),
            ('LP', (0.3, 1.0), '-', 'ET soil moisture threshold')
        ]
        
        for i, (name, bounds, unit, desc) in enumerate(lowland_params):
            ttk.Label(lowland_frame, text=f"{name} ({unit})").grid(row=i, column=0, sticky='w', padx=2)
            
            default = (bounds[0] + bounds[1]) / 2
            if name == 'LP':
                default = 0.7
            elif name == 'Imax':
                default = 2.0
            elif name == 'GWexch':
                default = 0.0
            
            var = tk.DoubleVar(value=default)
            self.param_vars[name] = var
            
            slider = ttk.Scale(lowland_frame, from_=bounds[0], to=bounds[1], variable=var,
                              orient=tk.HORIZONTAL, length=100,
                              command=lambda v, n=name: self.on_slider_change(n))
            slider.grid(row=i, column=1, padx=2)
            self.param_sliders[name] = slider
            
            entry_var = tk.StringVar(value=f"{default:.4f}")
            entry = ttk.Entry(lowland_frame, textvariable=entry_var, width=8)
            entry.grid(row=i, column=2, padx=2)
            entry.bind('<Return>', lambda e, n=name: self.on_entry_change(n))
            entry.bind('<FocusOut>', lambda e, n=name: self.on_entry_change(n))
            self.param_entries[name] = entry_var
        
        # Action buttons
        btn_frame = ttk.Frame(scrollable)
        btn_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(btn_frame, text="RUN CALIBRATION", command=self.run_model).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Run Validation", command=self.run_validation).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Run Projection", command=self.run_projection).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Export Projection", command=self.export_projection_results).pack(side=tk.LEFT, padx=3)
        
        btn_frame2 = ttk.Frame(scrollable)
        btn_frame2.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame2, text="Reset", command=self.reset_params).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame2, text="Use Optimized", command=self.use_calibrated).pack(side=tk.LEFT, padx=3)
        
        # Metrics
        metrics_frame = ttk.LabelFrame(scrollable, text="Calibration Metrics")
        metrics_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.metric_labels = {}
        for i, m in enumerate(['NSE', 'NSE_log', 'KGE', 'PBIAS', 'RMSE']):
            row, col = i // 3, i % 3
            ttk.Label(metrics_frame, text=f"{m}:").grid(row=row, column=col*2, sticky='w', padx=3)
            lbl = ttk.Label(metrics_frame, text="-", width=8)
            lbl.grid(row=row, column=col*2+1, sticky='w', padx=3)
            self.metric_labels[m] = lbl
        
        # Validation Metrics
        valid_metrics_frame = ttk.LabelFrame(parent, text="Validation Metrics")
        valid_metrics_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.valid_metric_labels = {}
        for i, m in enumerate(['NSE', 'NSE_log', 'KGE', 'PBIAS', 'RMSE']):
            row, col = i // 3, i % 3
            ttk.Label(valid_metrics_frame, text=f"{m}:").grid(row=row, column=col*2, sticky='w', padx=3)
            lbl = ttk.Label(valid_metrics_frame, text="-", width=8)
            lbl.grid(row=row, column=col*2+1, sticky='w', padx=3)
            self.valid_metric_labels[m] = lbl
    
    def create_optimization_tab(self, parent):
        """Automatic Optimization Tab with fix parameter option"""
        
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Method selection
        method_frame = ttk.LabelFrame(scrollable, text="Optimization Method")
        method_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.opt_method_var = tk.StringVar(value="DE")
        methods = [
            ("Differential Evolution (DE)", "DE"),
            ("Particle Swarm (PSO)", "PSO"),
            ("SCE-UA (Shuffled Complex)", "SCEUA"),
            ("Adaptive DE", "ADE"),
            ("Basin Hopping", "BH"),
            ("L-BFGS-B (Local)", "LBFGSB")
        ]
        for text, value in methods:
            ttk.Radiobutton(method_frame, text=text, variable=self.opt_method_var, value=value).pack(anchor='w', padx=5)
        
        # Settings
        set_frame = ttk.LabelFrame(scrollable, text="Settings")
        set_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(set_frame, text="Max Iterations:").grid(row=0, column=0, sticky='w', padx=5)
        self.maxiter_var = tk.StringVar(value="80")
        ttk.Entry(set_frame, textvariable=self.maxiter_var, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(set_frame, text="Population:").grid(row=1, column=0, sticky='w', padx=5)
        self.popsize_var = tk.StringVar(value="12")
        ttk.Entry(set_frame, textvariable=self.popsize_var, width=8).grid(row=1, column=1, padx=5)
        
        ttk.Label(set_frame, text="Tolerance:").grid(row=2, column=0, sticky='w', padx=5)
        self.tol_var = tk.StringVar(value="0.001")
        ttk.Entry(set_frame, textvariable=self.tol_var, width=8).grid(row=2, column=1, padx=5)
        
        # Convergence / Auto-stop settings
        conv_frame = ttk.LabelFrame(scrollable, text="Convergence / Auto-Stop")
        conv_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.auto_stop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(conv_frame, text="Auto-stop when converged (recommended)", 
                       variable=self.auto_stop_var).grid(row=0, column=0, columnspan=2, sticky='w', padx=5)
        
        ttk.Label(conv_frame, text="No-improvement limit:").grid(row=1, column=0, sticky='w', padx=5)
        self.no_improve_limit_var = tk.StringVar(value="50")
        ttk.Entry(conv_frame, textvariable=self.no_improve_limit_var, width=8).grid(row=1, column=1, padx=5)
        ttk.Label(conv_frame, text="(iterations without improvement)").grid(row=1, column=2, sticky='w', padx=5)
        
        ttk.Label(conv_frame, text="Min improvement:").grid(row=2, column=0, sticky='w', padx=5)
        self.min_improve_var = tk.StringVar(value="0.0001")
        ttk.Entry(conv_frame, textvariable=self.min_improve_var, width=8).grid(row=2, column=1, padx=5)
        ttk.Label(conv_frame, text="(objective function threshold)").grid(row=2, column=2, sticky='w', padx=5)
        
        # Weights
        wt_frame = ttk.LabelFrame(scrollable, text="Objective Weights")
        wt_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.weight_vars = {}
        for i, (k, v) in enumerate([('NSE', 0.4), ('NSE_log', 0.25), ('KGE', 0.25), ('PBIAS', 0.1)]):
            row, col = i // 2, i % 2
            ttk.Label(wt_frame, text=f"{k}:").grid(row=row, column=col*2, sticky='w', padx=5)
            var = tk.StringVar(value=str(v))
            self.weight_vars[k] = var
            ttk.Entry(wt_frame, textvariable=var, width=6).grid(row=row, column=col*2+1, padx=5)
        
        # Parameter selection with FIXED option
        param_frame = ttk.LabelFrame(scrollable, text="Parameters - Check to optimize")
        param_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Header
        ttk.Label(param_frame, text="Param", width=10).grid(row=0, column=0)
        ttk.Label(param_frame, text="Opt", width=4).grid(row=0, column=1)
        ttk.Label(param_frame, text="Min", width=8).grid(row=0, column=2)
        ttk.Label(param_frame, text="Max", width=8).grid(row=0, column=3)
        ttk.Label(param_frame, text="Fixed", width=8).grid(row=0, column=4)
        
        self.param_optimize_vars = {}
        self.param_min_vars = {}
        self.param_max_vars = {}
        self.param_fixed_vars = {}
        
        # Literature-based DEFAULT bounds for optimization
        # (Hock 2003; Seibert & Vis 2012; Lutz et al. 2016; Stigter et al. 2021)
        all_params_for_opt = [
            ('Tt',         (-3.0,   3.0),  '°C'),
            ('Cm',         (0.5,   12.0),  'mm/°C/d'),
            ('Csub',       (0.0,    1.0),  '0-1'),
            ('FC',         (10.0, 600.0),  'mm'),
            ('beta',       (0.5,    6.0),  '-'),
            ('alpha',      (0.01,  0.99),  '-'),
            ('Kq',         (0.01,  0.999), '1/d'),
            ('Ks',         (0.0001, 0.1),  '1/d'),
            ('lapse_rate', (4.0,   10.0),  '°C/km'),
            ('ETmult',     (0.3,    2.0),  '-'),
            ('Imax',       (0.0,    6.0),  'mm'),
            ('Ki',         (0.0001, 0.8),  '1/d'),
            ('GWexch',     (-3.0,   3.0),  'mm/d'),
            ('LP',         (0.1,    1.0),  '-')
        ]
        
        for i, (name, bounds, unit) in enumerate(all_params_for_opt):
            # Special defaults for new params
            if name == 'LP':
                default = 0.7
            elif name == 'Imax':
                default = 2.0
            elif name == 'GWexch':
                default = 0.0
            elif name == 'ETmult':
                default = 1.0
            elif name == 'Csub':
                default = 0.0
            elif name == 'Ks':
                default = 0.05
            elif name == 'Ki':
                default = 0.05
            elif name == 'FC':
                default = 300.0
            elif name == 'Cm':
                default = 6.0
            elif name == 'beta':
                default = 3.0
            elif name == 'lapse_rate':
                default = 7.0
            elif name == 'Tt':
                default = 0.0
            else:
                default = (bounds[0] + bounds[1]) / 2
            
            label_text = f"{name}"
            ttk.Label(param_frame, text=label_text).grid(row=i+1, column=0, sticky='w', padx=2)
            
            opt_var = tk.BooleanVar(value=True)
            self.param_optimize_vars[name] = opt_var
            ttk.Checkbutton(param_frame, variable=opt_var).grid(row=i+1, column=1)
            
            min_var = tk.StringVar(value=f"{bounds[0]}")
            self.param_min_vars[name] = min_var
            ttk.Entry(param_frame, textvariable=min_var, width=8).grid(row=i+1, column=2, padx=1)
            
            max_var = tk.StringVar(value=f"{bounds[1]}")
            self.param_max_vars[name] = max_var
            ttk.Entry(param_frame, textvariable=max_var, width=8).grid(row=i+1, column=3, padx=1)
            
            # Fixed value (used when not optimizing)
            fixed_var = tk.StringVar(value=f"{default:.4f}")
            self.param_fixed_vars[name] = fixed_var
            ttk.Entry(param_frame, textvariable=fixed_var, width=8).grid(row=i+1, column=4, padx=1)
        
        btn_row = len(all_params_for_opt) + 1
        ttk.Button(param_frame, text="Reset Default", command=self.reset_opt_bounds_default).grid(
            row=btn_row, column=0, pady=5, sticky='w', padx=2)
        ttk.Button(param_frame, text="Reset Extended", command=self.reset_opt_bounds).grid(
            row=btn_row, column=1, columnspan=2, pady=5, padx=2)
        ttk.Button(param_frame, text="Reset Very Extended", command=self.reset_opt_bounds_very_extended).grid(
            row=btn_row, column=3, pady=5, padx=2)
        ttk.Button(param_frame, text="Apply Optimized → Fixed", command=self.apply_optimized_to_fixed).grid(
            row=btn_row+1, column=0, columnspan=5, pady=5, padx=2)
        
        # Control buttons
        ctrl_frame = ttk.Frame(scrollable)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=10)
        
        self.opt_start_btn = ttk.Button(ctrl_frame, text="▶ START OPTIMIZATION", command=self.run_optimization)
        self.opt_start_btn.pack(side=tk.LEFT, padx=5)
        
        self.opt_stop_btn = ttk.Button(ctrl_frame, text="■ STOP", command=self.stop_optimization, state=tk.DISABLED)
        self.opt_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress
        prog_frame = ttk.Frame(scrollable)
        prog_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.opt_progress = ttk.Progressbar(prog_frame, maximum=100)
        self.opt_progress.pack(fill=tk.X, pady=2)
        
        self.opt_status = ttk.Label(prog_frame, text="Ready")
        self.opt_status.pack(anchor='w')
        
        self.opt_iter_label = ttk.Label(prog_frame, text="", foreground='blue')
        self.opt_iter_label.pack(anchor='w')
        
        # Results
        res_frame = ttk.LabelFrame(scrollable, text="Results")
        res_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.opt_results_text = ScrolledText(res_frame, height=10, font=('Consolas', 9))
        self.opt_results_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # History controls
        hist_frame = ttk.LabelFrame(scrollable, text="Iteration History")
        hist_frame.pack(fill=tk.X, padx=5, pady=5)
        
        hist_ctrl = ttk.Frame(hist_frame)
        hist_ctrl.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(hist_ctrl, text="Use iteration #:").pack(side=tk.LEFT, padx=3)
        self.hist_iter_var = tk.StringVar(value="")
        ttk.Entry(hist_ctrl, textvariable=self.hist_iter_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_ctrl, text="Apply", command=self.apply_history_iteration).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_ctrl, text="Show All History", command=self.show_iteration_history).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_ctrl, text="Export CSV", command=self.export_iteration_history).pack(side=tk.LEFT, padx=3)
    
    def create_glacier_tab(self, parent):
        """Glacier configuration with single and yearly folder support"""
        
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Load options
        load_frame = ttk.LabelFrame(scrollable, text="Load Glacier Data")
        load_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(load_frame, text="Load Single Shapefile (Average)", 
                  command=self.load_glacier_shp).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(load_frame, text="Load Yearly Folder", 
                  command=self.load_yearly_glacier_folder).pack(fill=tk.X, padx=5, pady=2)
        
        self.glacier_shp_status = ttk.Label(load_frame, text="○ Not loaded", foreground='gray')
        self.glacier_shp_status.pack(anchor='w', padx=5, pady=2)
        
        # Year range for yearly mode
        year_frame = ttk.Frame(load_frame)
        year_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(year_frame, text="Year Range:").pack(side=tk.LEFT, padx=3)
        self.glacier_start_year_var = tk.StringVar(value="2007")
        ttk.Entry(year_frame, textvariable=self.glacier_start_year_var, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Label(year_frame, text="to").pack(side=tk.LEFT, padx=3)
        self.glacier_end_year_var = tk.StringVar(value="2021")
        ttk.Entry(year_frame, textvariable=self.glacier_end_year_var, width=6).pack(side=tk.LEFT, padx=3)
        
        # Parameters
        gp_frame = ttk.LabelFrame(scrollable, text="Glacier Parameters")
        gp_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.glacier_param_vars = {}
        self.glacier_param_entries = {}
        
        for name, label, mn, mx, default in [
            ('ddf_clean', 'DDF Clean', 3.0, 12.0, 6.0),
            ('ddf_debris', 'DDF Debris', 1.0, 8.0, 3.0),
            ('lapse_rate', 'Lapse Rate', 4.0, 8.0, 6.0),
            ('t_melt', 'T Melt', -2.0, 2.0, 0.0),
            ('ref_elev', 'Ref Elev', 2500, 5000, 3400)
        ]:
            frame = ttk.Frame(gp_frame)
            frame.pack(fill=tk.X, padx=5, pady=1)
            
            ttk.Label(frame, text=label, width=12).pack(side=tk.LEFT)
            
            var = tk.DoubleVar(value=default)
            self.glacier_param_vars[name] = var
            
            slider = ttk.Scale(frame, from_=mn, to=mx, variable=var, orient=tk.HORIZONTAL, length=100,
                              command=lambda v, n=name: self._sync_glacier_entry(n))
            slider.pack(side=tk.LEFT, padx=3)
            
            # Entry for specific value
            entry_var = tk.StringVar(value=f"{default:.2f}")
            entry = ttk.Entry(frame, textvariable=entry_var, width=8)
            entry.pack(side=tk.LEFT, padx=3)
            entry.bind('<Return>', lambda e, n=name: self._sync_glacier_slider(n))
            entry.bind('<FocusOut>', lambda e, n=name: self._sync_glacier_slider(n))
            self.glacier_param_entries[name] = entry_var
        
        # Buttons
        btn_frame = ttk.Frame(scrollable)
        btn_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(btn_frame, text="RUN GLACIER MODEL", command=self.run_glacier_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Glacier Results", command=self.export_glacier_results).pack(side=tk.LEFT, padx=5)
        
        # ── Simulation Period ──
        period_frame = ttk.LabelFrame(scrollable, text="Simulation Period")
        period_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.glacier_period_var = tk.StringVar(value="calib_valid")
        for text, val in [("Calibration Only", "calib"),
                          ("Calib + Validation", "calib_valid"),
                          ("Full Data Range", "full"),
                          ("Custom", "custom")]:
            ttk.Radiobutton(period_frame, text=text, variable=self.glacier_period_var, 
                           value=val, command=self._update_glacier_dates).pack(anchor='w', padx=5)
        
        date_frame = ttk.Frame(period_frame)
        date_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(date_frame, text="Start:").grid(row=0, column=0, sticky='w', padx=3)
        self.glacier_sim_start_var = tk.StringVar(value="2007-01-01")
        self.glacier_sim_start_entry = ttk.Entry(date_frame, textvariable=self.glacier_sim_start_var, width=12)
        self.glacier_sim_start_entry.grid(row=0, column=1, padx=3)
        
        ttk.Label(date_frame, text="End:").grid(row=1, column=0, sticky='w', padx=3)
        self.glacier_sim_end_var = tk.StringVar(value="2021-12-31")
        self.glacier_sim_end_entry = ttk.Entry(date_frame, textvariable=self.glacier_sim_end_var, width=12)
        self.glacier_sim_end_entry.grid(row=1, column=1, padx=3)
        
        self._update_glacier_dates()  # Set initial dates
    
    def create_glacier_postcal_tab(self, parent):
        """Post-calibration glacier parameter tuning"""
        
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Initialize postcal state
        self.postcal_iteration_history = []
        self.postcal_best_results = []
        self.postcal_running = False
        self.postcal_stop_flag = False
        
        info_frame = ttk.Frame(scrollable)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="Glacier Post-Calibration", 
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        ttk.Label(info_frame, text="Tune glacier parameters after main model calibration",
                 foreground='gray').pack(anchor='w')
        
        # Status
        status_frame = ttk.LabelFrame(scrollable, text="Status")
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_status = ttk.Label(status_frame, text="Run main model calibration first", foreground='gray')
        self.postcal_status.pack(anchor='w', padx=5, pady=5)
        
        # Parameters - ALL glacier parameters
        param_frame = ttk.LabelFrame(scrollable, text="Glacier Parameters to Tune")
        param_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_param_vars = {}
        self.postcal_param_entries = {}
        
        glacier_params = [
            ('ddf_clean', 'DDF Clean Ice (mm/°C/day)', 3.0, 12.0, 6.0),
            ('ddf_debris', 'DDF Debris (mm/°C/day)', 1.0, 8.0, 3.0),
            ('lapse_rate', 'Lapse Rate (°C/km)', 4.0, 8.0, 6.0),
            ('t_melt', 'T Melt Threshold (°C)', -2.0, 2.0, 0.0),
            ('ref_elev', 'Reference Elevation (m)', 2500, 5000, 3400)
        ]
        
        for name, label, mn, mx, default in glacier_params:
            frame = ttk.Frame(param_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Label(frame, text=label, width=22).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=default)
            self.postcal_param_vars[name] = var
            
            slider = ttk.Scale(frame, from_=mn, to=mx, variable=var, orient=tk.HORIZONTAL, length=120,
                              command=lambda v, n=name: self._sync_postcal_entry(n))
            slider.pack(side=tk.LEFT, padx=3)
            
            # Entry for specific value
            entry_var = tk.StringVar(value=f"{default:.2f}")
            entry = ttk.Entry(frame, textvariable=entry_var, width=8)
            entry.pack(side=tk.LEFT, padx=3)
            entry.bind('<Return>', lambda e, n=name: self._sync_postcal_slider(n))
            entry.bind('<FocusOut>', lambda e, n=name: self._sync_postcal_slider(n))
            self.postcal_param_entries[name] = entry_var
        
        # Import from history
        hist_frame = ttk.LabelFrame(scrollable, text="Import from Optimization History")
        hist_frame.pack(fill=tk.X, padx=5, pady=5)
        
        hist_ctrl = ttk.Frame(hist_frame)
        hist_ctrl.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(hist_ctrl, text="Use iteration #:").pack(side=tk.LEFT, padx=3)
        self.postcal_hist_var = tk.StringVar(value="")
        ttk.Entry(hist_ctrl, textvariable=self.postcal_hist_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_ctrl, text="Apply", command=self.apply_history_to_postcal).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_ctrl, text="Show History", command=self.show_iteration_history).pack(side=tk.LEFT, padx=3)
        
        # Manual run button
        btn_frame = ttk.Frame(scrollable)
        btn_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(btn_frame, text="Run with Current Parameters", 
                  command=self.run_glacier_postcal).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Glacier Results", 
                  command=self.export_glacier_postcal_results).pack(side=tk.LEFT, padx=5)
        
        # Auto-tune section
        autotune_frame = ttk.LabelFrame(scrollable, text="Automatic Tuning")
        autotune_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(autotune_frame, text="Optimize glacier parameters to match observed flow",
                 foreground='gray').pack(anchor='w', padx=5)
        
        # Method selection (Item 8: added Basin Hopping)
        method_frame = ttk.Frame(autotune_frame)
        method_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_method_var = tk.StringVar(value="DE")
        ttk.Label(method_frame, text="Method:").pack(side=tk.LEFT, padx=3)
        for txt, val in [("DE", "DE"), ("Basin Hopping", "BH"), ("L-BFGS-B", "LBFGSB")]:
            ttk.Radiobutton(method_frame, text=txt, 
                           variable=self.postcal_method_var, value=val).pack(side=tk.LEFT, padx=3)
        
        # Settings
        settings_frame = ttk.Frame(autotune_frame)
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Max Iterations:").pack(side=tk.LEFT, padx=3)
        self.postcal_maxiter_var = tk.StringVar(value="30")
        ttk.Entry(settings_frame, textvariable=self.postcal_maxiter_var, width=6).pack(side=tk.LEFT, padx=3)
        
        # Parameter selection for auto-tune
        select_frame = ttk.Frame(autotune_frame)
        select_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(select_frame, text="Optimize:").pack(side=tk.LEFT, padx=3)
        
        self.postcal_opt_vars = {}
        for name in ['ddf_clean', 'ddf_debris', 'lapse_rate', 't_melt', 'ref_elev']:
            var = tk.BooleanVar(value=name in ['ddf_clean', 'ddf_debris'])  # Default: optimize DDFs
            self.postcal_opt_vars[name] = var
            ttk.Checkbutton(select_frame, text=name, variable=var).pack(side=tk.LEFT, padx=2)
        
        # Start / Stop buttons (Item 10)
        btn_tune_frame = ttk.Frame(autotune_frame)
        btn_tune_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_start_btn = ttk.Button(btn_tune_frame, text="▶ START AUTO-TUNE", 
                  command=self.auto_tune_glacier)
        self.postcal_start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        
        self.postcal_stop_btn = ttk.Button(btn_tune_frame, text="■ STOP", 
                  command=self.stop_glacier_autotune, state=tk.DISABLED)
        self.postcal_stop_btn.pack(side=tk.LEFT, padx=3)
        
        # Progress
        self.postcal_progress = ttk.Progressbar(autotune_frame, maximum=100)
        self.postcal_progress.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_iter_label = ttk.Label(autotune_frame, text="", foreground='blue')
        self.postcal_iter_label.pack(anchor='w', padx=5)
        
        # Metrics
        metrics_frame = ttk.LabelFrame(scrollable, text="Comparison Metrics")
        metrics_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.postcal_metrics = ttk.Label(metrics_frame, text="-")
        self.postcal_metrics.pack(anchor='w', padx=5, pady=5)
        
        # Item 12: Apply optimized params to Glacier tab
        apply_frame = ttk.LabelFrame(scrollable, text="Apply to Glacier Tab")
        apply_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(apply_frame, text="Copy optimized parameters to Glacier tab",
                 foreground='gray').pack(anchor='w', padx=5)
        ttk.Button(apply_frame, text="Apply Optimized Params to Glacier Tab", 
                  command=self.apply_postcal_to_glacier_tab).pack(fill=tk.X, padx=5, pady=5)
        
        # Item 9: History, Export, Apply iteration
        history_frame = ttk.LabelFrame(scrollable, text="Iteration History")
        history_frame.pack(fill=tk.X, padx=5, pady=5)
        
        hist_btn_frame = ttk.Frame(history_frame)
        hist_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(hist_btn_frame, text="Show All History", 
                  command=self.show_postcal_history).pack(side=tk.LEFT, padx=3)
        ttk.Button(hist_btn_frame, text="Export CSV", 
                  command=self.export_postcal_history_csv).pack(side=tk.LEFT, padx=3)
        
        apply_iter_frame = ttk.Frame(history_frame)
        apply_iter_frame.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(apply_iter_frame, text="Apply iteration #:").pack(side=tk.LEFT, padx=3)
        self.postcal_apply_iter_var = tk.StringVar(value="")
        ttk.Entry(apply_iter_frame, textvariable=self.postcal_apply_iter_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(apply_iter_frame, text="Apply", 
                  command=self.apply_postcal_iteration).pack(side=tk.LEFT, padx=3)
        
        # Results
        results_frame = ttk.LabelFrame(scrollable, text="Auto-Tune Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.postcal_results_text = ScrolledText(results_frame, height=8, font=('Consolas', 9))
        self.postcal_results_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_ungauged_tab(self, parent):
        """Ungauged catchment modeling - run model without calibration"""
        
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Info
        info_frame = ttk.Frame(scrollable)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="Ungauged Catchment Modeling", 
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        ttk.Label(info_frame, text="Run model with calibrated parameters (no calibration needed)",
                 foreground='gray').pack(anchor='w')
        
        # Catchment info
        catch_frame = ttk.LabelFrame(scrollable, text="Catchment Information")
        catch_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.ungauged_vars = {}
        for label, key, default in [("Name:", "name", ""), ("Area (km²):", "area", "500"),
                                    ("Latitude:", "lat", "35.0")]:
            frame = ttk.Frame(catch_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=label, width=12).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            self.ungauged_vars[key] = var
            ttk.Entry(frame, textvariable=var, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(catch_frame, text="Load from Shapefile", 
                  command=self.load_ungauged_shapefile).pack(fill=tk.X, padx=5, pady=5)
        
        # Data loading
        data_frame = ttk.LabelFrame(scrollable, text="Input Data (Required)")
        data_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.ungauged_status = {}
        
        ttk.Button(data_frame, text="Load Temperature", 
                  command=self.load_ungauged_temp).pack(fill=tk.X, padx=5, pady=2)
        self.ungauged_status['temp'] = ttk.Label(data_frame, text="○ Not loaded", foreground='gray')
        self.ungauged_status['temp'].pack(anchor='w', padx=5)
        
        ttk.Button(data_frame, text="Load Precipitation", 
                  command=self.load_ungauged_precip).pack(fill=tk.X, padx=5, pady=2)
        self.ungauged_status['precip'] = ttk.Label(data_frame, text="○ Not loaded", foreground='gray')
        self.ungauged_status['precip'].pack(anchor='w', padx=5)
        
        ttk.Button(data_frame, text="Load Elevation Bands (Recommended)", 
                  command=self.load_ungauged_elev_bands).pack(fill=tk.X, padx=5, pady=2)
        self.ungauged_status['elev_bands'] = ttk.Label(data_frame, text="○ Not loaded (highly recommended)", foreground='gray')
        self.ungauged_status['elev_bands'].pack(anchor='w', padx=5)
        
        # Item 13: Manual elevation bands entry
        manual_elev_frame = ttk.LabelFrame(scrollable, text="Manual Elevation Bands (alternative to file)")
        manual_elev_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(manual_elev_frame, text="Enter comma-separated elevation centers (m):", 
                 foreground='gray').pack(anchor='w', padx=5)
        self.ungauged_elev_centers_var = tk.StringVar(value="3500, 4000, 4500, 5000")
        ttk.Entry(manual_elev_frame, textvariable=self.ungauged_elev_centers_var, width=40).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(manual_elev_frame, text="Enter comma-separated area fractions (sum ≈ 1.0):", 
                 foreground='gray').pack(anchor='w', padx=5)
        self.ungauged_elev_fracs_var = tk.StringVar(value="0.25, 0.35, 0.25, 0.15")
        ttk.Entry(manual_elev_frame, textvariable=self.ungauged_elev_fracs_var, width=40).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(manual_elev_frame, text="Apply Manual Bands", 
                  command=self.apply_manual_ungauged_elev_bands).pack(fill=tk.X, padx=5, pady=3)
        
        # Optional data
        opt_frame = ttk.LabelFrame(scrollable, text="Optional Data")
        opt_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Item 14: Glacier melt source selection
        ttk.Label(opt_frame, text="Glacier Melt Source:", foreground='gray').pack(anchor='w', padx=5)
        
        self.ungauged_glacier_source_var = tk.StringVar(value="none")
        glacier_src_frame = ttk.Frame(opt_frame)
        glacier_src_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Radiobutton(glacier_src_frame, text="None", 
                       variable=self.ungauged_glacier_source_var, value="none").pack(anchor='w')
        ttk.Radiobutton(glacier_src_frame, text="Upload file (m³/s)", 
                       variable=self.ungauged_glacier_source_var, value="file").pack(anchor='w')
        ttk.Radiobutton(glacier_src_frame, text="Use from Glacier Tab (current results)", 
                       variable=self.ungauged_glacier_source_var, value="tab").pack(anchor='w')
        
        ttk.Button(opt_frame, text="Load Glacier Melt File (m³/s)", 
                  command=self.load_ungauged_glacier).pack(fill=tk.X, padx=5, pady=2)
        self.ungauged_status['glacier'] = ttk.Label(opt_frame, text="○ Not loaded (optional)", foreground='gray')
        self.ungauged_status['glacier'].pack(anchor='w', padx=5)
        
        ttk.Button(opt_frame, text="Load Observed Flow (for comparison)", 
                  command=self.load_ungauged_obs).pack(fill=tk.X, padx=5, pady=2)
        self.ungauged_status['obs'] = ttk.Label(opt_frame, text="○ Not loaded (optional)", foreground='gray')
        self.ungauged_status['obs'].pack(anchor='w', padx=5)
        
        # Period
        period_frame = ttk.LabelFrame(scrollable, text="Simulation Period")
        period_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(period_frame, text="Start:").grid(row=0, column=0, padx=5, pady=2)
        self.ungauged_start_var = tk.StringVar(value="2007-01-01")
        ttk.Entry(period_frame, textvariable=self.ungauged_start_var, width=12).grid(row=0, column=1, padx=5)
        
        ttk.Label(period_frame, text="End:").grid(row=1, column=0, padx=5, pady=2)
        self.ungauged_end_var = tk.StringVar(value="2021-12-31")
        ttk.Entry(period_frame, textvariable=self.ungauged_end_var, width=12).grid(row=1, column=1, padx=5)
        
        # Parameters
        param_frame = ttk.LabelFrame(scrollable, text="Model Parameters")
        param_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(param_frame, text="Use calibrated parameters or set custom values",
                 foreground='gray').pack(anchor='w', padx=5)
        
        btn_frame = ttk.Frame(param_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Use Calibrated", 
                  command=self.use_calibrated_for_ungauged).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Use History #", 
                  command=self.use_history_for_ungauged).pack(side=tk.LEFT, padx=3)
        self.ungauged_hist_var = tk.StringVar(value="")
        ttk.Entry(btn_frame, textvariable=self.ungauged_hist_var, width=6).pack(side=tk.LEFT, padx=3)
        
        self.ungauged_param_vars = {}
        
        # All parameters
        all_params_ungauged = [
            ('Tt', (-3.0, 3.0), '°C'),
            ('Cm', (1.0, 10.0), 'mm/°C/d'),
            ('Csub', (0.0, 0.5), 'mm/°C/d'),
            ('FC', (50.0, 600.0), 'mm'),
            ('beta', (1.0, 5.0), '-'),
            ('alpha', (0.05, 0.95), '-'),
            ('Kq', (0.05, 0.95), '1/d'),
            ('Ks', (0.001, 0.15), '1/d'),
            ('lapse_rate', (4.0, 8.0), '°C/km'),
                                    ('ETmult', (0.5, 1.5), '-'),
            ('Imax', (0.0, 5.0), 'mm'),
            ('Ki', (0.001, 0.3), '1/d'),
            ('GWexch', (-3.0, 3.0), 'mm/d'),
            ('LP', (0.3, 1.0), '-')
        ]
        
        for i, (name, bounds, unit) in enumerate(all_params_ungauged):
            # Special defaults for new params
            if name == 'LP':
                default = 0.7
            elif name == 'Imax':
                default = 2.0
            elif name == 'GWexch':
                default = 0.0
            elif name == 'ETmult':
                default = 1.0
            else:
                default = (bounds[0] + bounds[1]) / 2
            
            frame = ttk.Frame(param_frame)
            frame.pack(fill=tk.X, padx=5, pady=1)
            
            # Mark NEW parameters
            ttk.Label(frame, text=f"{name}:", width=12).pack(side=tk.LEFT)
            var = tk.StringVar(value=f"{default:.4f}")
            self.ungauged_param_vars[name] = var
            ttk.Entry(frame, textvariable=var, width=12).pack(side=tk.LEFT, padx=5)
        

        
        # Run button
        run_frame = ttk.Frame(scrollable)
        run_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(run_frame, text="RUN UNGAUGED MODEL", 
                  command=self.run_ungauged_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frame, text="Export Results", 
                  command=self.export_ungauged_results).pack(side=tk.LEFT, padx=5)
        
        # Metrics (if observed available)
        metrics_frame = ttk.LabelFrame(scrollable, text="Comparison Metrics (if observed available)")
        metrics_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.ungauged_metrics_label = ttk.Label(metrics_frame, text="-")
        self.ungauged_metrics_label.pack(anchor='w', padx=5, pady=5)
    
    def create_sens_tab(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Info
        info_frame = ttk.Frame(scrollable)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(info_frame, text="Sensitivity Analysis", 
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        
        frame = ttk.Frame(scrollable)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(frame, text="Samples per param:").pack(side=tk.LEFT, padx=5)
        self.sens_n_var = tk.StringVar(value="20")
        ttk.Entry(frame, textvariable=self.sens_n_var, width=6).pack(side=tk.LEFT, padx=5)
        
        # Parameter selection for sensitivity
        sens_param_frame = ttk.LabelFrame(scrollable, text="Parameters to Analyze")
        sens_param_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.sens_param_vars = {}
        
        all_sens_params = [
            ('Tt', 'Temperature threshold'),
            ('Cm', 'Melt coefficient'),
            ('Csub', 'Sublimation coeff.'),
            ('FC', 'Field capacity'),
            ('beta', 'Runoff shape'),
            ('alpha', 'Quick flow fraction'),
            ('Kq', 'Quick recession'),
            ('Ks', 'Slow recession'),
            ('lapse_rate', 'Temperature lapse'),
            
            ('ETmult', 'ET correction'),
            ('Imax', 'Interception'),
            ('Ki', 'Interflow'),
            ('GWexch', 'GW exchange'),
            ('LP', 'ET threshold')
        ]
        
        for i, (name, desc) in enumerate(all_sens_params):
            var = tk.BooleanVar(value=True)
            self.sens_param_vars[name] = var
            row = i // 2
            col = i % 2
            ttk.Checkbutton(sens_param_frame, text=f"{name}: {desc}", 
                           variable=var).grid(row=row, column=col, sticky='w', padx=5, pady=1)
        
        btn_frame = ttk.Frame(scrollable)
        btn_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(btn_frame, text="RUN SENSITIVITY", command=self.run_sensitivity).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Results", command=self.export_sensitivity_results).pack(side=tk.LEFT, padx=5)
        
        self.sens_progress = ttk.Progressbar(scrollable, maximum=100)
        self.sens_progress.pack(fill=tk.X, padx=5, pady=5)
        
        self.sens_results_text = ScrolledText(scrollable, height=15, font=('Consolas', 9))
        self.sens_results_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_right_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Calibration
        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="Calibration")
        self.fig1, self.ax1 = plt.subplots(figsize=(10, 5))
        self.canvas1 = FigureCanvasTkAgg(self.fig1, master=tab1)
        self.canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas1, tab1)
        
        # Validation
        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="Validation")
        self.fig2, self.ax2 = plt.subplots(figsize=(10, 5))
        self.canvas2 = FigureCanvasTkAgg(self.fig2, master=tab2)
        self.canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas2, tab2)
        
        # Comprehensive
        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="Comprehensive")
        self.fig3, self.axes3 = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
        self.canvas3 = FigureCanvasTkAgg(self.fig3, master=tab3)
        self.canvas3.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas3, tab3)
        
        # Comprehensive Validation
        tab3v = ttk.Frame(notebook)
        notebook.add(tab3v, text="Comprehensive (Valid)")
        self.fig3v, self.axes3v = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
        self.canvas3v = FigureCanvasTkAgg(self.fig3v, master=tab3v)
        self.canvas3v.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas3v, tab3v)
        
        # Projection
        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="Projection")
        self.fig4, self.ax4 = plt.subplots(figsize=(10, 5))
        self.canvas4 = FigureCanvasTkAgg(self.fig4, master=tab4)
        self.canvas4.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas4, tab4)
        
        # Glacier
        tab5 = ttk.Frame(notebook)
        notebook.add(tab5, text="Glacier")
        self.fig5, self.axes5 = plt.subplots(2, 2, figsize=(10, 8))
        self.canvas5 = FigureCanvasTkAgg(self.fig5, master=tab5)
        self.canvas5.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas5, tab5)
        
        # Ungauged
        tab_ungauged = ttk.Frame(notebook)
        notebook.add(tab_ungauged, text="Ungauged")
        self.fig_ungauged, self.ax_ungauged = plt.subplots(figsize=(10, 5))
        self.canvas_ungauged = FigureCanvasTkAgg(self.fig_ungauged, master=tab_ungauged)
        self.canvas_ungauged.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas_ungauged, tab_ungauged)
        
        # Sensitivity - 5x3 grid for 14 parameters
        tab6 = ttk.Frame(notebook)
        notebook.add(tab6, text="Sensitivity")
        self.fig6, self.axes6 = plt.subplots(5, 3, figsize=(14, 16))
        self.canvas6 = FigureCanvasTkAgg(self.fig6, master=tab6)
        self.canvas6.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas6, tab6)
    
    # =========================================================================
    # PARAMETER HANDLING
    # =========================================================================
    
    def on_slider_change(self, name):
        val = self.param_vars[name].get()
        self.param_entries[name].set(f"{val:.4f}")
    
    def on_entry_change(self, name):
        try:
            val = float(self.param_entries[name].get())
            
            # Only apply very wide absolute safety limits (physical constraints)
            # No clamping to slider bounds - user has full manual control
            absolute_limits = {
                'Tt': (-20.0, 20.0), 'Cm': (0.0, 50.0), 'Csub': (0.0, 5.0), 'FC': (0.0, 5000.0),
                'beta': (0.01, 20.0), 'alpha': (0.0001, 0.9999), 'Kq': (0.0001, 0.9999),
                'Ks': (0.000001, 0.9999), 'lapse_rate': (0.0, 20.0),
                'ETmult': (0.0, 5.0), 'Imax': (0.0, 30.0), 'Ki': (0.000001, 0.9999),
                'GWexch': (-20.0, 20.0), 'LP': (0.0, 1.0)
            }
            
            if name in absolute_limits:
                lo, hi = absolute_limits[name]
                val = max(lo, min(hi, val))
            
            self.param_vars[name].set(val)
            self.param_entries[name].set(f"{val:.4f}")
        except ValueError:
            pass
    
    def update_slider_bounds(self):
        """Update slider bounds based on selection (Standard/Extended/VeryExtended)."""
        # All parameters with bounds for each level
        bounds_standard = {
            'Tt': (-3.0, 3.0), 'Cm': (0.5, 12.0), 'Csub': (0.0, 1.0), 'FC': (10.0, 600.0),
            'beta': (0.5, 6.0), 'alpha': (0.05, 0.95), 'Kq': (0.01, 0.999),
            'Ks': (0.0001, 0.1), 'lapse_rate': (4.0, 10.0),
            'ETmult': (0.3, 2.0), 'Imax': (0.0, 6.0), 'Ki': (0.001, 0.8),
            'GWexch': (-3.0, 3.0), 'LP': (0.1, 1.0)
        }
        bounds_extended = {
            'Tt': (-6.0, 6.0), 'Cm': (0.3, 20.0), 'Csub': (0.0, 1.0), 'FC': (10.0, 1500.0),
            'beta': (0.3, 8.0), 'alpha': (0.01, 0.99), 'Kq': (0.001, 0.999),
            'Ks': (0.0001, 0.5), 'lapse_rate': (2.0, 12.0),
            'ETmult': (0.3, 2.0), 'Imax': (0.0, 10.0), 'Ki': (0.0001, 0.8),
            'GWexch': (-5.0, 5.0), 'LP': (0.1, 1.0)
        }
        bounds_very_extended = {
            'Tt': (-10.0, 10.0), 'Cm': (0.1, 30.0), 'Csub': (0.0, 2.0), 'FC': (5.0, 2000.0),
            'beta': (0.1, 10.0), 'alpha': (0.001, 0.999), 'Kq': (0.0001, 0.9999),
            'Ks': (0.00001, 0.9), 'lapse_rate': (1.0, 15.0),
            'ETmult': (0.0, 3.0), 'Imax': (0.0, 15.0), 'Ki': (0.00001, 0.9999),
            'GWexch': (-10.0, 10.0), 'LP': (0.01, 1.0)
        }
        
        # Determine which bounds to use
        if hasattr(self, 'bounds_selection_var'):
            selection = self.bounds_selection_var.get()
            if selection == 'VeryExtended':
                bounds = bounds_very_extended
            elif selection == 'Extended':
                bounds = bounds_extended
            else:
                bounds = bounds_standard
        elif self.ext_bounds_var.get():
            bounds = bounds_extended
        else:
            bounds = bounds_standard
        
        # Update all sliders
        for name, (bmin, bmax) in bounds.items():
            if name in self.param_sliders:
                self.param_sliders[name].config(from_=bmin, to=bmax)
    
    def reset_params(self):
        """Reset all parameters to default values (all params)."""
        # All parameters with their default bounds
        all_params = [
            ('Tt', (-3.0, 3.0)),
            ('Cm', (1.0, 10.0)),
            ('Csub', (0.0, 0.5)),
            ('FC', (50.0, 600.0)),
            ('beta', (1.0, 5.0)),
            ('alpha', (0.05, 0.95)),
            ('Kq', (0.05, 0.95)),
            ('Ks', (0.001, 0.15)),
            ('lapse_rate', (4.0, 8.0)),
                                    ('ETmult', (0.5, 1.5)),
            ('Imax', (0.0, 5.0)),
            ('Ki', (0.001, 0.3)),
            ('GWexch', (-3.0, 3.0)),
            ('LP', (0.3, 1.0))
        ]
        
        for name, bounds in all_params:
            if name in self.param_vars:
                if name == 'LP':
                    default = 0.7
                elif name == 'Imax':
                    default = 2.0
                elif name == 'GWexch':
                    default = 0.0
                elif name == 'ETmult':
                    default = 1.0
                elif name == 'Csub':
                    default = 0.0
                else:
                    default = (bounds[0] + bounds[1]) / 2
                self.param_vars[name].set(default)
                if name in self.param_entries:
                    self.param_entries[name].set(f"{default:.4f}")
        
        self.log("All parameters reset to defaults")
    
    def reset_opt_bounds_default(self):
        """Reset optimization bounds to DEFAULT (literature-based) ranges.
        
        References: Hock (2003), Seibert & Vis (2012), Lutz et al. (2016),
                    Stigter et al. (2021), Immerzeel et al. (2010, 2014)
        """
        all_params_default = [
            ('Tt',         (-3.0,   3.0)),   # Hock 2003; Singh et al. 2000
            ('Cm',         (0.5,   12.0)),   # Hock 2003; glacier ice up to 12
            ('Csub',       (0.0,    1.0)),   # Stigter et al. 2021; fraction
            ('FC',         (10.0, 600.0)),   # Seibert 1999; HKH: 100-500 mm
            ('beta',       (0.5,    6.0)),   # Bergstrom 1992; Seibert & Vis 2012
            ('alpha',      (0.01,  0.99)),
            ('Kq',         (0.01,  0.999)),  # Seibert & Vis 2012; upper zone
            ('Ks',         (0.0001, 0.1)),   # Seibert 1999; baseflow recession
            ('lapse_rate', (4.0,   10.0)),   # Immerzeel 2014; Palazzi 2013
            ('ETmult',     (0.3,    2.0)),   # Bergstrom 1992; Seibert 1999
            ('Imax',       (0.0,    6.0)),   # Rutter et al. 1971
            ('Ki',         (0.0001, 0.8)),
            ('GWexch',     (-3.0,   3.0)),   # Seibert 1999
            ('LP',         (0.1,    1.0))    # Seibert & Vis 2012; HBV standard
        ]
        self._apply_opt_bounds(all_params_default)
        self.log("Optimization bounds reset to DEFAULT (literature-based) ranges")
    
    def reset_opt_bounds(self):
        """Reset optimization bounds to EXTENDED ranges (wider than literature defaults).
        
        These are the former default ranges, kept for challenging/data-scarce catchments.
        """
        all_params_extended = [
            ('Tt',         (-6.0,   6.0)),
            ('Cm',         (0.3,   20.0)),
            ('Csub',       (0.0,    1.0)),
            ('FC',         (10.0, 1500.0)),
            ('beta',       (0.3,    8.0)),
            ('alpha',      (0.01,  0.99)),
            ('Kq',         (0.001, 0.999)),
            ('Ks',         (0.0001, 0.5)),
            ('lapse_rate', (2.0,   12.0)),
            ('ETmult',     (0.3,    2.0)),
            ('Imax',       (0.0,   10.0)),
            ('Ki',         (0.0001, 0.8)),
            ('GWexch',     (-5.0,   5.0)),
            ('LP',         (0.1,    1.0))
        ]
        self._apply_opt_bounds(all_params_extended)
        self.log("Optimization bounds reset to EXTENDED ranges")
    
    def reset_opt_bounds_very_extended(self):
        """Reset optimization bounds to VERY EXTENDED (widest) ranges."""
        all_params_very_extended = [
            ('Tt', (-10.0, 10.0)),
            ('Cm', (0.1, 30.0)),
            ('Csub', (0.0, 2.0)),
            ('FC', (5.0, 2000.0)),
            ('beta', (0.1, 10.0)),
            ('alpha', (0.001, 0.999)),
            ('Kq', (0.0001, 0.9999)),
            ('Ks', (0.00001, 0.9)),
            ('lapse_rate', (1.0, 15.0)),
            ('ETmult', (0.0, 3.0)),
            ('Imax', (0.0, 15.0)),
            ('Ki', (0.00001, 0.9999)),
            ('GWexch', (-10.0, 10.0)),
            ('LP', (0.01, 1.0))
        ]
        self._apply_opt_bounds(all_params_very_extended)
        self.log("Optimization bounds reset to VERY EXTENDED ranges")
    
    def _apply_opt_bounds(self, params_list):
        """Helper to apply a set of bounds to the optimization tab."""
        for name, bounds in params_list:
            if name in self.param_min_vars:
                if name == 'LP':
                    default = 0.7
                elif name == 'Imax':
                    default = 2.0
                elif name == 'GWexch':
                    default = 0.0
                elif name == 'ETmult':
                    default = 1.0
                elif name == 'Csub':
                    default = 0.0
                else:
                    default = (bounds[0] + bounds[1]) / 2
                self.param_min_vars[name].set(str(bounds[0]))
                self.param_max_vars[name].set(str(bounds[1]))
                self.param_fixed_vars[name].set(f"{default:.4f}")
                self.param_optimize_vars[name].set(True)
    
    def apply_optimized_to_fixed(self):
        """Copy stored optimized parameter values to Fixed column.
        
        Uses the preserved optimized params (not current GUI values),
        allowing multi-round optimization with fixed parameters.
        """
        params = None
        if self.stored_optimized_params:
            params = self.stored_optimized_params
        elif self.best_results:
            _, params, _ = self.best_results[0]
        
        if params:
            count = 0
            for name in self.param_fixed_vars:
                if name in params:
                    self.param_fixed_vars[name].set(f"{params[name]:.4f}")
                    count += 1
            self.log(f"Applied {count} optimized values to Fixed column. "
                     f"Uncheck parameters you want to keep fixed for next optimization round.")
        else:
            # Fallback: use current GUI values
            count = 0
            for name in self.param_fixed_vars:
                if name in self.param_vars:
                    val = self.param_vars[name].get()
                    self.param_fixed_vars[name].set(f"{val:.4f}")
                    count += 1
            self.log(f"No stored optimized params. Applied {count} current GUI values to Fixed column.")
    
    def use_calibrated(self):
        """Restore optimized parameters from last optimization to GUI sliders/entries.
        
        Uses stored_optimized_params (set during optimization completion) which
        is never overwritten by manual parameter changes or manual calibration runs.
        Falls back to best_results[0] if available.
        """
        params = None
        source = None
        
        # Priority 1: Stored optimized params (preserved from optimization)
        if self.stored_optimized_params:
            params = self.stored_optimized_params
            source = "stored optimization result"
        # Priority 2: Best results from optimization history
        elif self.best_results:
            _, params, _ = self.best_results[0]
            source = "best result from optimization history"
        # Priority 3: Current model params (legacy fallback)
        elif self.hydro_model and self.hydro_model.params:
            params = self.hydro_model.params
            source = "current model (may include manual changes)"
        
        if params:
            for name, val in params.items():
                if name in self.param_vars:
                    self.param_vars[name].set(val)
                    if name in self.param_entries:
                        self.param_entries[name].set(f"{val:.4f}")
            self.log(f"Restored {len(params)} optimized parameters from {source}")
        else:
            self.log("No optimized parameters available. Run optimization first.")
    
    # =========================================================================
    # DATA LOADING
    # =========================================================================
    
    def _browse_base_path(self):
        """Browse for base catchments folder."""
        path = filedialog.askdirectory(title="Select Catchments Base Folder")
        if path:
            self.base_path_var.set(path)
    
    def auto_load_catchment_data(self):
        """Auto-load all data for a catchment from standard folder structure.
        
        Expected structure:
            {base_path}/{name}/PPT/CHIRPS_{name}_*.nc
            {base_path}/{name}/Temperature/GLDAS_Temp_{name}_*.nc
            {base_path}/{name}/Streamflow_data/calib.csv
            {base_path}/{name}/Streamflow_data/valid.csv
            {base_path}/{name}/Glacier_polygon/Glacier_Melt/{name}_glacier_melt_hec_hms.csv  (optional)
            {base_path}/{name}/Catchment_Characteristics/{name}_Elevation_Bands.xlsx|csv  (optional)
        """
        base = self.base_path_var.get().strip()
        name = self.auto_catchment_var.get().strip()
        
        if not name:
            messagebox.showwarning("Warning", "Enter catchment folder name")
            return
        
        catchment_dir = os.path.join(base, name)
        if not os.path.isdir(catchment_dir):
            messagebox.showerror("Error", f"Folder not found:\n{catchment_dir}")
            return
        
        loaded = []
        failed = []
        
        # Set catchment name
        self.entry_vars['catchment_name'].set(name)
        
        # 0. Shapefile for area/location
        shp_file = None
        for shp_dir_name in ["shapefile", "Shapefile", "Catchment_polygon", "Catchment_Shapefile", ""]:
            shp_dir = os.path.join(catchment_dir, shp_dir_name) if shp_dir_name else catchment_dir
            if not os.path.isdir(shp_dir):
                continue
            shp_file = self._find_file(shp_dir, f"{name}_UTM.shp", f"{name}*.shp", f"*{name}*.shp", "*.shp")
            if shp_file:
                self.log(f"  Found shapefile: {shp_file}")
                break
        
        if shp_file:
            try:
                info = extract_shapefile_info(shp_file)
                if info:
                    self.entry_vars['area'].set(f"{info['area_km2']:.2f}")
                    self.entry_vars['lat'].set(f"{info['latitude']:.4f}")
                    self.entry_vars['lon'].set(f"{info['longitude']:.4f}")
                    loaded.append(f"Shapefile ({info['area_km2']:.1f} km²)")
                    self.log(f"  Area={info['area_km2']:.2f} km², Lat={info['latitude']:.4f}, Lon={info['longitude']:.4f}")
                else:
                    failed.append("Shapefile: load returned None (install: pip install pyshp)")
                    self.log(f"  Shapefile load returned None - install pyshp or geopandas")
            except Exception as e:
                failed.append(f"Shapefile: {e}")
                self.log(f"  Shapefile error: {e}")
        else:
            failed.append("Shapefile: not found (set area manually)")
            self.log(f"  No shapefile found in {catchment_dir}")
        
        # 1. Precipitation
        ppt_dir = os.path.join(catchment_dir, "PPT")
        ppt_file = self._find_file(ppt_dir, f"CHIRPS_{name}_*.nc", f"*{name}*.nc", "*.nc")
        if ppt_file:
            try:
                self.precip_data = load_timeseries(ppt_file)
                self.status_labels['precip'].config(text=f"✓ {len(self.precip_data)} days", foreground='green')
                loaded.append("Precipitation")
            except Exception as e:
                failed.append(f"Precipitation: {e}")
        else:
            failed.append("Precipitation: no file found in PPT/")
        
        # 2. Temperature
        temp_dir = os.path.join(catchment_dir, "Temperature")
        temp_file = self._find_file(temp_dir, f"GLDAS_Temp_{name}_*.nc", f"*{name}*.nc", "*.nc")
        if temp_file:
            try:
                self.temp_data = load_timeseries(temp_file)
                self.status_labels['temp'].config(text=f"✓ {len(self.temp_data)} days", foreground='green')
                loaded.append("Temperature")
            except Exception as e:
                failed.append(f"Temperature: {e}")
        else:
            failed.append("Temperature: no file found in Temperature/")
        
        # 3. Calibration flow
        flow_dir = os.path.join(catchment_dir, "Streamflow_data")
        if not os.path.isdir(flow_dir):
            flow_dir = os.path.join(catchment_dir, "Streamflow_data_HMS")
        calib_file = os.path.join(flow_dir, "calib.csv")
        if os.path.isfile(calib_file):
            try:
                self.obs_flow_calib = load_csv_timeseries(calib_file)
                n = len(self.obs_flow_calib)
                s, e = self.obs_flow_calib.index[0], self.obs_flow_calib.index[-1]
                self.status_labels['flow_cal'].config(text=f"✓ {n} days", foreground='green')
                self.calib_start_var.set(s.strftime('%Y-%m-%d'))
                self.calib_end_var.set(e.strftime('%Y-%m-%d'))
                loaded.append("Calib Flow")
            except Exception as e:
                failed.append(f"Calib Flow: {e}")
        else:
            failed.append("Calib Flow: calib.csv not found")
        
        # 4. Validation flow
        valid_file = os.path.join(flow_dir, "valid.csv")
        if os.path.isfile(valid_file):
            try:
                self.obs_flow_valid = load_csv_timeseries(valid_file)
                n = len(self.obs_flow_valid)
                s, e = self.obs_flow_valid.index[0], self.obs_flow_valid.index[-1]
                self.status_labels['flow_val'].config(text=f"✓ {n} days", foreground='green')
                self.valid_start_var.set(s.strftime('%Y-%m-%d'))
                self.valid_end_var.set(e.strftime('%Y-%m-%d'))
                loaded.append("Valid Flow")
            except Exception as e:
                failed.append(f"Valid Flow: {e}")
        else:
            failed.append("Valid Flow: valid.csv not found")
        
        # 5. Glacier melt (optional - skip silently if not found)
        glacier_dir = os.path.join(catchment_dir, "Glacier_polygon", "Glacier_Melt")
        glacier_file = self._find_file(glacier_dir, f"{name}_glacier_melt_hec_hms.csv", f"*{name}*glacier*.csv", "*.csv")
        if glacier_file:
            try:
                self.glacier_melt_input = load_csv_timeseries(glacier_file)
                self.status_labels['glacier_melt'].config(text=f"✓ {len(self.glacier_melt_input)} days", foreground='green')
                loaded.append("Glacier Melt")
            except Exception as e:
                failed.append(f"Glacier: {e}")
        
        # 6. Elevation bands (optional)
        elev_dir = os.path.join(catchment_dir, "Catchment_Characteristics")
        elev_file = self._find_file(elev_dir, f"{name}_Elevation_Bands.xlsx", f"{name}_Elevation_Bands.csv",
                                     f"*Elevation*Band*.xlsx", f"*Elevation*Band*.csv")
        if elev_file:
            try:
                info = self.elevation_bands.load_from_file(elev_file)
                self.elev_bands_status.config(
                    text=f"✓ {info['n_bands']} bands, ref={info['ref_elev']:.0f}m", foreground='green')
                self.update_elev_bands_display()
                loaded.append(f"Elevation Bands ({info['n_bands']})")
            except Exception as e:
                failed.append(f"Elevation Bands: {e}")
        
        # Summary
        msg = f"Auto-load for '{name}':\n"
        if loaded:
            msg += f"  ✓ Loaded: {', '.join(loaded)}\n"
        if failed:
            msg += f"  ✗ Not found/failed: {', '.join(failed)}\n"
        
        self.log(msg)
        n_loaded = len(loaded)
        self.auto_load_status.config(
            text=f"✓ {n_loaded} loaded" + (f", {len(failed)} skipped" if failed else ""),
            foreground='green' if n_loaded >= 3 else 'orange')
    
    @staticmethod
    def _find_file(directory, *patterns):
        """Find first matching file in directory using multiple glob patterns."""
        if not os.path.isdir(directory):
            return None
        for pattern in patterns:
            matches = glob.glob(os.path.join(directory, pattern))
            if matches:
                return matches[0]
        return None
    
    def load_temperature(self):
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.nc")])
        if fp:
            try:
                self.temp_data = load_timeseries(fp)
                self.status_labels['temp'].config(text=f"✓ {len(self.temp_data)} days", foreground='green')
                self.log(f"Temperature: {len(self.temp_data)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_precipitation(self):
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.nc")])
        if fp:
            try:
                self.precip_data = load_timeseries(fp)
                self.status_labels['precip'].config(text=f"✓ {len(self.precip_data)} days", foreground='green')
                self.log(f"Precipitation: {len(self.precip_data)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_calib_flow(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                self.obs_flow_calib = load_csv_timeseries(fp)
                n = len(self.obs_flow_calib)
                s, e = self.obs_flow_calib.index[0], self.obs_flow_calib.index[-1]
                self.status_labels['flow_cal'].config(text=f"✓ {n} days", foreground='green')
                self.log(f"Calib flow: {n} days")
                self.calib_start_var.set(s.strftime('%Y-%m-%d'))
                self.calib_end_var.set(e.strftime('%Y-%m-%d'))
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_valid_flow(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                self.obs_flow_valid = load_csv_timeseries(fp)
                n = len(self.obs_flow_valid)
                s, e = self.obs_flow_valid.index[0], self.obs_flow_valid.index[-1]
                self.status_labels['flow_val'].config(text=f"✓ {n} days", foreground='green')
                self.log(f"Valid flow: {n} days")
                self.valid_start_var.set(s.strftime('%Y-%m-%d'))
                self.valid_end_var.set(e.strftime('%Y-%m-%d'))
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_single_flow_file(self):
        """Load a single flow file and split into calibration/validation based on period settings."""
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                flow = load_csv_timeseries(fp)
                n = len(flow)
                s, e = flow.index[0], flow.index[-1]
                
                # Split by calibration/validation periods
                calib_start = pd.Timestamp(self.calib_start_var.get())
                calib_end = pd.Timestamp(self.calib_end_var.get())
                valid_start = pd.Timestamp(self.valid_start_var.get())
                valid_end = pd.Timestamp(self.valid_end_var.get())
                
                self.obs_flow_calib = flow[(flow.index >= calib_start) & (flow.index <= calib_end)]
                self.obs_flow_valid = flow[(flow.index >= valid_start) & (flow.index <= valid_end)]
                
                nc = len(self.obs_flow_calib)
                nv = len(self.obs_flow_valid)
                
                self.status_labels['flow_cal'].config(
                    text=f"✓ {nc} days (from single file)", foreground='green')
                self.status_labels['flow_val'].config(
                    text=f"✓ {nv} days (from single file)", foreground='green')
                self.single_flow_status.config(
                    text=f"✓ {n} days total → Calib: {nc}, Valid: {nv}", foreground='green')
                self.log(f"Single flow file: {n} days → Calib: {nc} days, Valid: {nv} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_swe_observed(self):
        """Load observed SWE data for visualization in comprehensive plot."""
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                df = pd.read_csv(fp, parse_dates=True)
                # Find date column
                date_col = None
                for c in df.columns:
                    if c.lower() in ['date', 'datetime', 'time']:
                        date_col = c
                        break
                if date_col is None:
                    date_col = df.columns[0]
                
                # Find SWE column
                swe_col = None
                for c in df.columns:
                    if c.lower() in ['swe_mm', 'swe', 'snow_water_equivalent']:
                        swe_col = c
                        break
                if swe_col is None:
                    # Try second column
                    swe_col = df.columns[1] if len(df.columns) > 1 else None
                
                if swe_col is None:
                    messagebox.showerror("Error", "Could not find SWE column (look for 'SWE_mm' or 'SWE')")
                    return
                
                df[date_col] = pd.to_datetime(df[date_col])
                self.swe_obs_data = pd.Series(df[swe_col].values, index=df[date_col])
                n = len(self.swe_obs_data)
                s, e = self.swe_obs_data.index[0], self.swe_obs_data.index[-1]
                self.status_labels['swe_obs'].config(text=f"✓ {n} days ({s.date()} to {e.date()})", foreground='green')
                self.log(f"SWE observed: {n} days, column '{swe_col}'")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_glacier_melt_csv(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                self.glacier_melt_input = load_csv_timeseries(fp)
                self.status_labels['glacier_melt'].config(text=f"✓ {len(self.glacier_melt_input)} days", foreground='green')
                self.log(f"Glacier melt: {len(self.glacier_melt_input)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_catchment_shp(self):
        fp = filedialog.askopenfilename(filetypes=[("Shapefile", "*.shp")])
        if fp:
            info = extract_shapefile_info(fp)
            if info:
                self.entry_vars['area'].set(f"{info['area_km2']:.2f}")
                self.entry_vars['lat'].set(f"{info['latitude']:.4f}")
                self.entry_vars['lon'].set(f"{info['longitude']:.4f}")
                self.entry_vars['catchment_name'].set(Path(fp).stem.replace('_UTM', ''))
                self.log(f"Catchment: {info['area_km2']:.2f} km²")
    
    def load_glacier_shp(self):
        fp = filedialog.askopenfilename(filetypes=[("Shapefile", "*.shp")])
        if fp:
            try:
                self.glacier_model = GlacierMeltModel()
                info = self.glacier_model.load_glacier_shapefile(fp)
                self.glacier_shp_status.config(text=f"✓ Single: {info['n_glaciers']} glaciers, {info['total_area']:.2f} km²", foreground='green')
                self.log(f"Glacier: {info['n_glaciers']} glaciers, {info['total_area']:.2f} km²")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_yearly_glacier_folder(self):
        folder = filedialog.askdirectory(title="Select Yearly Glacier Folder")
        if folder:
            try:
                start_year = int(self.glacier_start_year_var.get())
                end_year = int(self.glacier_end_year_var.get())
                
                self.glacier_model = GlacierMeltModel()
                info = self.glacier_model.load_yearly_folder(folder, start_year, end_year)
                
                self.glacier_shp_status.config(
                    text=f"✓ Yearly: {info['years_loaded']} years, ~{info['total_area']:.2f} km²", 
                    foreground='green')
                self.log(f"Yearly glaciers: {info['years_loaded']} years loaded")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_elev_bands(self):
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.xlsx *.xls")])
        if fp:
            try:
                info = self.elevation_bands.load_from_file(fp)
                self.elev_bands_status.config(
                    text=f"✓ {info['n_bands']} bands, ref={info['ref_elev']:.0f}m", foreground='green')
                self.update_elev_bands_display()
                self.log(f"Elevation bands: {info['n_bands']}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def apply_manual_elev_bands(self):
        text = self.elev_bands_text.get('1.0', tk.END).strip()
        if not text:
            return
        try:
            elevations, areas = [], []
            for line in text.split('\n'):
                if line.strip():
                    parts = line.replace(',', ' ').split()
                    if len(parts) >= 2:
                        elevations.append(float(parts[0]))
                        areas.append(float(parts[1]))
            
            self.elevation_bands.set_manual(elevations, areas=areas)
            info = self.elevation_bands.get_summary()
            self.elev_bands_status.config(
                text=f"✓ {info['n_bands']} bands", foreground='green')
            self.update_elev_bands_display()
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def clear_elev_bands(self):
        self.elevation_bands.clear()
        self.elev_bands_status.config(text="○ Not loaded (lumped)", foreground='gray')
        self.update_elev_bands_display()
    
    def update_elev_bands_display(self):
        self.elev_bands_display.config(state=tk.NORMAL)
        self.elev_bands_display.delete('1.0', tk.END)
        self.elev_bands_display.insert('1.0', self.elevation_bands.get_bands_table())
        self.elev_bands_display.config(state=tk.DISABLED)
    
    # =========================================================================
    # MODEL RUNNING
    # =========================================================================
    
    def prepare_data(self, start, end, with_glacier=True):
        dates = pd.date_range(start, end, freq='D')
        area = float(self.entry_vars['area'].get())
        
        precip = self.precip_data.reindex(dates).fillna(0).values
        temp = self.temp_data.reindex(dates).interpolate().bfill().ffill().values
        
        glacier_mm = np.zeros(len(dates))
        opt = self.glacier_opt_var.get()
        
        if with_glacier and opt != 'none':
            if opt == 'external' and self.glacier_melt_input is not None:
                g = self.glacier_melt_input.reindex(dates).fillna(0).values
                glacier_mm = g * SECONDS_PER_DAY / (area * 1e6) * 1000
            elif opt == 'integrated' and self.glacier_results is not None:
                g = pd.Series(self.glacier_results['total_m3s'], index=self.glacier_results['dates']).reindex(dates).fillna(0).values
                glacier_mm = g * SECONDS_PER_DAY / (area * 1e6) * 1000
        
        return dates, precip, temp, glacier_mm
    
    def run_model(self):
        if self.temp_data is None or self.precip_data is None:
            messagebox.showerror("Error", "Load temperature and precipitation first")
            return
        
        try:
            area = float(self.entry_vars['area'].get())
            lat = float(self.entry_vars['lat'].get())
            warmup = int(self.warmup_var.get())
            spinup_years = int(self.spinup_var.get()) if hasattr(self, 'spinup_var') else 2
            
            start = pd.Timestamp(self.calib_start_var.get())
            end = pd.Timestamp(self.calib_end_var.get())
            
            with_gl = self.glacier_calib_var.get() == 'with'
            dates, precip, temp, glacier_mm = self.prepare_data(start, end, with_glacier=with_gl)
            
            obs = self.obs_flow_calib.reindex(dates).values if self.obs_flow_calib is not None else None
            
            # Get catchment type and configure model
            ctype = self.catchment_type_var.get() if hasattr(self, 'catchment_type_var') else 'Universal'
            
            if self.hydro_model is None:
                self.hydro_model = HKPHydroModel(area_km2=area, latitude=lat, catchment_type=ctype)
            else:
                self.hydro_model.area_km2 = area
                self.hydro_model.latitude = lat
                self.hydro_model.catchment_type = ctype
                self.hydro_model._configure_for_catchment_type()
            
            # Apply module settings from GUI
            if hasattr(self, 'use_snow_var'):
                self.hydro_model.use_snow = self.use_snow_var.get()
                self.hydro_model.use_sublimation = self.use_sublimation_var.get()
                self.hydro_model.use_interception = self.use_intercept_var.get()
                self.hydro_model.use_interflow = self.use_interflow_var.get()
                self.hydro_model.use_gw_exchange = self.use_gw_var.get()
            
            self.hydro_model.elevation_bands = self.elevation_bands
            
            # Get all parameters
            params = {}
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ki', 'Ks', 
                               'lapse_rate', 'Imax', 'GWexch', 'ETmult', 'LP']
            for n in all_param_names:
                if n in self.param_vars:
                    params[n] = self.param_vars[n].get()
            
            # Backward compatibility - fill missing with defaults
            if 'Ki' not in params:
                params['Ki'] = 0.05
            if 'Imax' not in params:
                params['Imax'] = 0.0
            if 'GWexch' not in params:
                params['GWexch'] = 0.0
            if 'ETmult' not in params:
                params['ETmult'] = 1.0
            if 'LP' not in params:
                params['LP'] = 0.7
            
            self.hydro_model.set_params(params)
            
            # Use spinup for proper state initialization (critical for CSV data)
            if spinup_years > 0:
                self.results_calib = self.hydro_model.run_with_spinup(
                    precip, temp, dates, glacier_mm, params, spinup_years=spinup_years)
            else:
                self.results_calib = self.hydro_model.run(precip, temp, dates, glacier_mm, params)
            
            self.results_calib['dates'] = dates
            self.results_calib['obs'] = obs
            self.results_calib['precip'] = precip
            self.results_calib['temp'] = temp
            
            if not with_gl:
                _, _, _, glacier_full = self.prepare_data(start, end, with_glacier=True)
                g_m3s = glacier_full * area * 1e6 / (SECONDS_PER_DAY * 1000)
                self.results_calib['Q_sim_m3s'] = self.results_calib['Q_sim_m3s'] + g_m3s
            
            if obs is not None:
                m = calc_all_metrics(obs, self.results_calib['Q_sim_m3s'], warmup)
                self.hydro_model.calibration_metrics = m
                for k, v in m.items():
                    txt = f"{v:.1f}%" if k == 'PBIAS' else f"{v:.3f}" if k != 'RMSE' else f"{v:.1f}"
                    self.metric_labels[k].config(text=txt)
            
            self.plot_calibration()
            self.plot_comprehensive()
            
            # Log glacier status
            opt = self.glacier_opt_var.get()
            if opt != 'none':
                if np.sum(glacier_mm) > 0 or (not with_gl):
                    gl_info = f"mode={opt}, calib_with={with_gl}"
                    if with_gl:
                        self.log(f"Calibration run complete (Mode: {ctype}, glacier: {gl_info}, mean={np.mean(glacier_mm):.3f} mm/d)")
                    else:
                        self.log(f"Calibration run complete (Mode: {ctype}, glacier added post-hoc)")
                else:
                    self.log(f"Calibration run complete (Mode: {ctype})")
                    self.log(f"⚠ WARNING: Glacier mode '{opt}' active but glacier data is zero for calibration period!")
            else:
                self.log(f"Calibration run complete (Mode: {ctype}, no glacier)")
            
            self.postcal_status.config(text="Main model calibrated - can tune glacier params", foreground='green')
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
            traceback.print_exc()
    
    def run_validation(self):
        try:
            area = float(self.entry_vars['area'].get())
            lat = float(self.entry_vars['lat'].get())
            warmup = int(self.warmup_var.get())
            spinup_years = int(self.spinup_var.get()) if hasattr(self, 'spinup_var') else 2
            
            start = pd.Timestamp(self.valid_start_var.get())
            end = pd.Timestamp(self.valid_end_var.get())
            
            # Get catchment type
            ctype = self.catchment_type_var.get() if hasattr(self, 'catchment_type_var') else 'Universal'
            
            # Create or update model (same as run_model for consistency)
            if self.hydro_model is None:
                self.hydro_model = HKPHydroModel(area_km2=area, latitude=lat, catchment_type=ctype)
            else:
                self.hydro_model.area_km2 = area
                self.hydro_model.latitude = lat
                self.hydro_model.catchment_type = ctype
                self.hydro_model._configure_for_catchment_type()
            
            # Apply module settings from GUI
            if hasattr(self, 'use_snow_var'):
                self.hydro_model.use_snow = self.use_snow_var.get()
                self.hydro_model.use_sublimation = self.use_sublimation_var.get()
                self.hydro_model.use_interception = self.use_intercept_var.get()
                self.hydro_model.use_interflow = self.use_interflow_var.get()
                self.hydro_model.use_gw_exchange = self.use_gw_var.get()
            
            self.hydro_model.elevation_bands = self.elevation_bands
            
            # Get ALL 14 parameters from GUI (same as run_model)
            params = {}
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ki', 'Ks', 
                               'lapse_rate', 'Imax', 'GWexch', 'ETmult', 'LP']
            for n in all_param_names:
                if n in self.param_vars:
                    params[n] = self.param_vars[n].get()
            
            # Backward compatibility defaults
            for n, d in [('Ki', 0.05), ('Imax', 0.0), ('GWexch', 0.0), ('ETmult', 1.0), ('LP', 0.7)]:
                if n not in params:
                    params[n] = d
            
            self.hydro_model.set_params(params)
            
            # Use same glacier mode as calibration (consistency!)
            with_gl = self.glacier_calib_var.get() == 'with'
            opt = self.glacier_opt_var.get()
            dates, precip, temp, glacier_mm = self.prepare_data(start, end, with_glacier=with_gl)
            
            # Check if glacier is expected but truly missing
            if opt != 'none' and with_gl and np.sum(glacier_mm) == 0:
                self.log("WARNING: Glacier mode is active but glacier data is zero for validation period!")
                messagebox.showwarning("Glacier Warning", 
                    "Glacier mode is active but no glacier data covers the validation period.\n\n"
                    "Go to Glacier tab → set period to 'Calib + Validation' → re-run glacier model.")
            elif opt != 'none' and not with_gl:
                _, _, _, glacier_check = self.prepare_data(start, end, with_glacier=True)
                if np.sum(glacier_check) == 0:
                    self.log("WARNING: No glacier data for validation period (post-hoc addition will be zero)")
                    messagebox.showwarning("Glacier Warning", 
                        "Calibrate-without-glacier mode: no glacier data covers validation period.\n\n"
                        "Go to Glacier tab → set period to 'Calib + Validation' → re-run glacier model.")
            
            obs = None
            if self.obs_flow_valid is not None:
                obs = self.obs_flow_valid.reindex(dates).values
            elif self.obs_flow_calib is not None:
                obs = self.obs_flow_calib.reindex(dates).values
            
            # USE SPINUP - same as run_model and optimization (critical fix!)
            if spinup_years > 0:
                self.results_valid = self.hydro_model.run_with_spinup(
                    precip, temp, dates, glacier_mm, params, spinup_years=spinup_years)
            else:
                self.results_valid = self.hydro_model.run(precip, temp, dates, glacier_mm, params)
            
            self.results_valid['dates'] = dates
            self.results_valid['obs'] = obs
            self.results_valid['precip'] = precip
            self.results_valid['temp'] = temp
            
            # If calibrated WITHOUT glacier, add glacier post-hoc (same as calibration logic)
            if not with_gl and opt != 'none':
                _, _, _, glacier_full = self.prepare_data(start, end, with_glacier=True)
                if np.sum(glacier_full) > 0:
                    g_m3s = glacier_full * area * 1e6 / (SECONDS_PER_DAY * 1000)
                    self.results_valid['Q_sim_m3s'] = self.results_valid['Q_sim_m3s'] + g_m3s
                    self.log(f"Validation: glacier added post-hoc (mean = {np.mean(g_m3s):.4f} m3/s)")
            
            if obs is not None:
                m = calc_all_metrics(obs, self.results_valid['Q_sim_m3s'], warmup)
                for k, v in m.items():
                    txt = f"{v:.1f}%" if k == 'PBIAS' else f"{v:.3f}" if k != 'RMSE' else f"{v:.1f}"
                    self.valid_metric_labels[k].config(text=txt)
            
            # Log glacier contribution
            if np.sum(glacier_mm) > 0:
                self.log(f"Validation: {start.date()} to {end.date()} (spinup={spinup_years}yr, glacier: mean={np.mean(glacier_mm):.3f} mm/d)")
            else:
                self.log(f"Validation: {start.date()} to {end.date()} (spinup={spinup_years}yr, no glacier)")
            
            self.plot_validation()
            self.plot_comprehensive_validation()
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def run_projection(self):
        try:
            area = float(self.entry_vars['area'].get())
            lat = float(self.entry_vars['lat'].get())
            spinup_years = int(self.spinup_var.get()) if hasattr(self, 'spinup_var') else 2
            
            start = pd.Timestamp(self.proj_start_var.get())
            end = pd.Timestamp(self.proj_end_var.get())
            
            ctype = self.catchment_type_var.get() if hasattr(self, 'catchment_type_var') else 'Universal'
            
            if self.hydro_model is None:
                self.hydro_model = HKPHydroModel(area_km2=area, latitude=lat, catchment_type=ctype)
            else:
                self.hydro_model.area_km2 = area
                self.hydro_model.latitude = lat
            
            if hasattr(self, 'use_snow_var'):
                self.hydro_model.use_snow = self.use_snow_var.get()
                self.hydro_model.use_sublimation = self.use_sublimation_var.get()
                self.hydro_model.use_interception = self.use_intercept_var.get()
                self.hydro_model.use_interflow = self.use_interflow_var.get()
                self.hydro_model.use_gw_exchange = self.use_gw_var.get()
            
            self.hydro_model.elevation_bands = self.elevation_bands
            
            # Get ALL 14 parameters from GUI
            params = {}
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ki', 'Ks', 
                               'lapse_rate', 'Imax', 'GWexch', 'ETmult', 'LP']
            for n in all_param_names:
                if n in self.param_vars:
                    params[n] = self.param_vars[n].get()
            for n, d in [('Ki', 0.05), ('Imax', 0.0), ('GWexch', 0.0), ('ETmult', 1.0), ('LP', 0.7)]:
                if n not in params:
                    params[n] = d
            
            self.hydro_model.set_params(params)
            
            # Use same glacier mode as calibration
            with_gl = self.glacier_calib_var.get() == 'with'
            opt = self.glacier_opt_var.get()
            dates, precip, temp, glacier_mm = self.prepare_data(start, end, with_glacier=with_gl)
            
            # Warn if glacier expected but missing
            if opt != 'none' and np.sum(glacier_mm) == 0:
                self.log("WARNING: Glacier mode active but no glacier data for projection period!")
            
            obs = None
            for flow_data in [self.obs_flow_calib, self.obs_flow_valid]:
                if flow_data is not None:
                    aligned = flow_data.reindex(dates)
                    if aligned.notna().sum() > 0:
                        obs = aligned.values
                        break
            
            # USE SPINUP - consistent with calibration and validation
            if spinup_years > 0:
                self.results_proj = self.hydro_model.run_with_spinup(
                    precip, temp, dates, glacier_mm, params, spinup_years=spinup_years)
            else:
                self.results_proj = self.hydro_model.run(precip, temp, dates, glacier_mm, params)
            
            self.results_proj['dates'] = dates
            self.results_proj['obs'] = obs
            
            # If calibrated WITHOUT glacier, add post-hoc
            if not with_gl and opt != 'none':
                _, _, _, glacier_full = self.prepare_data(start, end, with_glacier=True)
                if np.sum(glacier_full) > 0:
                    g_m3s = glacier_full * area * 1e6 / (SECONDS_PER_DAY * 1000)
                    self.results_proj['Q_sim_m3s'] = self.results_proj['Q_sim_m3s'] + g_m3s
            
            self.plot_projection()
            self.log(f"Projection: {start.date()} to {end.date()} (spinup={spinup_years}yr)")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    # =========================================================================
    # GLACIER SLIDER SYNCHRONIZATION
    # =========================================================================
    
    def _sync_glacier_entry(self, name):
        """Update entry when glacier slider changes"""
        val = self.glacier_param_vars[name].get()
        self.glacier_param_entries[name].set(f"{val:.2f}")
    
    def _sync_glacier_slider(self, name):
        """Update slider when glacier entry changes"""
        try:
            val = float(self.glacier_param_entries[name].get())
            self.glacier_param_vars[name].set(val)
        except ValueError:
            pass
    
    def _sync_postcal_entry(self, name):
        """Update entry when postcal slider changes"""
        val = self.postcal_param_vars[name].get()
        self.postcal_param_entries[name].set(f"{val:.2f}")
    
    def _sync_postcal_slider(self, name):
        """Update slider when postcal entry changes"""
        try:
            val = float(self.postcal_param_entries[name].get())
            self.postcal_param_vars[name].set(val)
        except ValueError:
            pass
    
    def _update_glacier_dates(self):
        """Update glacier simulation date fields based on period selection."""
        mode = self.glacier_period_var.get()
        
        if mode == 'custom':
            # Enable entries for manual editing
            if hasattr(self, 'glacier_sim_start_entry'):
                self.glacier_sim_start_entry.config(state='normal')
                self.glacier_sim_end_entry.config(state='normal')
            return
        
        if mode == 'calib':
            start = self.calib_start_var.get()
            end = self.calib_end_var.get()
        elif mode == 'calib_valid':
            start = self.calib_start_var.get()
            end = self.valid_end_var.get()
        elif mode == 'full':
            if self.temp_data is not None:
                start = self.temp_data.index[0].strftime('%Y-%m-%d')
                end = self.temp_data.index[-1].strftime('%Y-%m-%d')
            else:
                start = self.calib_start_var.get()
                end = self.valid_end_var.get()
        else:
            return
        
        # Set dates and disable entries for preset modes
        if hasattr(self, 'glacier_sim_start_entry'):
            self.glacier_sim_start_entry.config(state='normal')
            self.glacier_sim_end_entry.config(state='normal')
            self.glacier_sim_start_var.set(start)
            self.glacier_sim_end_var.set(end)
            self.glacier_sim_start_entry.config(state='disabled')
            self.glacier_sim_end_entry.config(state='disabled')
    
    def run_glacier_model(self):
        if self.glacier_model is None:
            messagebox.showerror("Error", "Load glacier data first")
            return
        if self.temp_data is None:
            messagebox.showerror("Error", "Load temperature first")
            return
        
        try:
            # Use glacier tab's own date range
            start = pd.Timestamp(self.glacier_sim_start_var.get())
            end = pd.Timestamp(self.glacier_sim_end_var.get())
            dates = pd.date_range(start, end, freq='D')
            
            temp = self.temp_data.reindex(dates).interpolate().bfill().ffill().values
            
            params = {k: v.get() for k, v in self.glacier_param_vars.items()}
            self.glacier_model.set_params(params)
            
            self.glacier_results = self.glacier_model.run(temp, dates, params)
            
            mean_melt = np.mean(self.glacier_results['total_m3s'])
            period = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
            self.log(f"Glacier melt ({period}): mean = {mean_melt:.4f} m³/s, {len(dates)} days")
            
            self.plot_glacier_results()
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def run_glacier_postcal(self):
        """Run glacier model with post-calibration parameters."""
        if self.glacier_model is None or self.results_calib is None:
            messagebox.showinfo("Info", "Run main calibration and load glacier data first")
            return
        
        try:
            dates = self.results_calib['dates']
            temp = self.results_calib['temp']
            
            # Get parameters from sliders/entries
            params = self.glacier_model.params.copy()
            for k, v in self.postcal_param_vars.items():
                try:
                    # Try entry first
                    if k in self.postcal_param_entries:
                        params[k] = float(self.postcal_param_entries[k].get())
                    else:
                        params[k] = v.get()
                except:
                    params[k] = v.get()
            
            results = self.glacier_model.run(temp, dates, params)
            
            # Calculate metrics
            area = float(self.entry_vars['area'].get())
            warmup = int(self.warmup_var.get())
            
            # Get base simulation (without glacier if calibrated without)
            if self.glacier_calib_var.get() == 'without':
                # Add glacier to base simulation
                new_sim = self.results_calib['Q_sim_m3s'] + results['total_m3s']
            else:
                # Recalculate with new glacier
                glacier_mm = results['total_m3s'] * SECONDS_PER_DAY / (area * 1e6) * 1000
                new_results = self.hydro_model.run(
                    self.results_calib['precip'], temp, dates, glacier_mm
                )
                new_sim = new_results['Q_sim_m3s']
            
            obs = self.results_calib.get('obs')
            if obs is not None:
                m = calc_all_metrics(obs, new_sim, warmup)
                self.postcal_metrics.config(
                    text=f"NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}  PBIAS={m['PBIAS']:.1f}%  RMSE={m['RMSE']:.1f}")
            
            self.log("Glacier post-calibration run complete")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def stop_glacier_autotune(self):
        """Stop the glacier auto-tune process."""
        self.postcal_stop_flag = True
        self.log("Stopping glacier auto-tune...")
    
    def auto_tune_glacier(self):
        """Automatically tune glacier parameters using optimization."""
        if self.glacier_model is None or self.results_calib is None:
            messagebox.showinfo("Info", "Run main calibration and load glacier data first")
            return
        
        if self.obs_flow_calib is None:
            messagebox.showinfo("Info", "Need observed flow for auto-tuning")
            return
        
        if self.postcal_running:
            return
        
        self.postcal_running = True
        self.postcal_stop_flag = False
        self.postcal_iteration_history = []
        self.postcal_best_results = []
        self.postcal_start_btn.config(state=tk.DISABLED)
        self.postcal_stop_btn.config(state=tk.NORMAL)
        
        # Run in thread
        threading.Thread(target=self._auto_tune_glacier_thread, daemon=True).start()
    
    def _auto_tune_glacier_thread(self):
        try:
            dates = self.results_calib['dates']
            temp = self.results_calib['temp']
            obs = self.results_calib.get('obs')
            area = float(self.entry_vars['area'].get())
            warmup = int(self.warmup_var.get())
            maxiter = int(self.postcal_maxiter_var.get())
            method = self.postcal_method_var.get()
            
            # Build bounds for selected parameters
            param_bounds_dict = {
                'ddf_clean': (3.0, 12.0),
                'ddf_debris': (1.0, 8.0),
                'lapse_rate': (4.0, 8.0),
                't_melt': (-2.0, 2.0),
                'ref_elev': (2500, 5000)
            }
            
            bounds = []
            param_names = []
            fixed_params = {}
            
            for name in ['ddf_clean', 'ddf_debris', 'lapse_rate', 't_melt', 'ref_elev']:
                if self.postcal_opt_vars[name].get():
                    bounds.append(param_bounds_dict[name])
                    param_names.append(name)
                else:
                    fixed_params[name] = self.postcal_param_vars[name].get()
            
            if len(bounds) == 0:
                self.root.after(0, lambda: messagebox.showinfo("Info", "Select at least one parameter to optimize"))
                self.root.after(0, self._finish_postcal_cleanup)
                return
            
            self.root.after(0, lambda: self.postcal_progress.configure(value=0))
            self.root.after(0, lambda: self.postcal_iter_label.config(text="Starting..."))
            
            iteration_count = [0]
            best_obj = [999]
            
            def objective(x):
                if self.postcal_stop_flag:
                    raise StopIteration("User stopped")
                
                # Build full params
                params = fixed_params.copy()
                for i, name in enumerate(param_names):
                    params[name] = x[i]
                
                try:
                    # Run glacier model
                    results = self.glacier_model.run(temp, dates, params)
                    
                    # Calculate combined discharge
                    if self.glacier_calib_var.get() == 'without':
                        sim = self.results_calib['Q_sim_m3s'] + results['total_m3s']
                    else:
                        glacier_mm = results['total_m3s'] * SECONDS_PER_DAY / (area * 1e6) * 1000
                        new_results = self.hydro_model.run(
                            self.results_calib['precip'], temp, dates, glacier_mm
                        )
                        sim = new_results['Q_sim_m3s']
                    
                    # Calculate metrics
                    o, s = obs[warmup:], sim[warmup:]
                    mask = ~(np.isnan(o) | np.isnan(s))
                    if mask.sum() < 10:
                        return float(1e6)
                    
                    nse = float(calc_nse(o[mask], s[mask]))
                    kge = float(calc_kge(o[mask], s[mask]))
                    pbias = float(calc_pbias(o[mask], s[mask]))
                    
                    obj = float((1 - nse) * 0.5 + (1 - kge) * 0.5)
                    
                    iteration_count[0] += 1
                    
                    # Store history (Item 9)
                    self.postcal_iteration_history.append({
                        'iteration': iteration_count[0],
                        'params': params.copy(),
                        'obj': obj,
                        'NSE': nse,
                        'KGE': kge,
                        'PBIAS': pbias
                    })
                    
                    # Track best results
                    if len(self.postcal_best_results) < 3 or obj < self.postcal_best_results[-1][0]:
                        self.postcal_best_results.append((obj, params.copy(), {'NSE': nse, 'KGE': kge, 'PBIAS': pbias}))
                        self.postcal_best_results.sort(key=lambda x: x[0])
                        self.postcal_best_results = self.postcal_best_results[:3]
                    
                    if obj < best_obj[0]:
                        best_obj[0] = obj
                    
                    # Update progress
                    if iteration_count[0] % 3 == 0:
                        progress = min(95, iteration_count[0] / (maxiter * len(bounds) * 10) * 100)
                        self.root.after(0, lambda p=progress, n=nse, k=kge, ic=iteration_count[0]: 
                                       self._update_postcal_progress(p, n, k, ic))
                    
                    if not np.isfinite(obj):
                        return float(1e6)
                    return float(obj)
                except StopIteration:
                    raise
                except:
                    return float(1e6)
            
            try:
                # Run optimization (Item 8: added Basin Hopping)
                if method == "DE":
                    result = differential_evolution(objective, bounds, maxiter=maxiter, 
                                                   popsize=8, tol=0.01, seed=42)
                    x_opt = result.x
                elif method == "BH":
                    initial = [(b[0]+b[1])/2 for b in bounds]
                    result = basinhopping(objective, initial, 
                                         minimizer_kwargs={"method": "L-BFGS-B", "bounds": bounds},
                                         niter=maxiter, seed=42)
                    x_opt = result.x
                else:  # LBFGSB
                    initial = [(b[0]+b[1])/2 for b in bounds]
                    result = minimize(objective, initial, method='L-BFGS-B', bounds=bounds,
                                     options={'maxiter': maxiter})
                    x_opt = result.x
                
                stop_reason = "Complete"
            except StopIteration:
                stop_reason = "Stopped by user"
                if self.postcal_best_results:
                    _, best_p, best_m = self.postcal_best_results[0]
                    self.root.after(0, lambda p=best_p, m=best_m, r=stop_reason: 
                                   self._finish_glacier_autotune(p, m, r))
                else:
                    self.root.after(0, lambda: self._finish_postcal_cleanup())
                return
            
            # Build final params
            final_params = fixed_params.copy()
            for i, name in enumerate(param_names):
                final_params[name] = x_opt[i]
            
            # Calculate final metrics
            results = self.glacier_model.run(temp, dates, final_params)
            if self.glacier_calib_var.get() == 'without':
                sim = self.results_calib['Q_sim_m3s'] + results['total_m3s']
            else:
                glacier_mm = results['total_m3s'] * SECONDS_PER_DAY / (area * 1e6) * 1000
                new_results = self.hydro_model.run(
                    self.results_calib['precip'], temp, dates, glacier_mm
                )
                sim = new_results['Q_sim_m3s']
            
            final_metrics = calc_all_metrics(obs, sim, warmup)
            
            # Update UI
            self.root.after(0, lambda p=final_params, m=final_metrics, r=stop_reason: 
                           self._finish_glacier_autotune(p, m, r))
            
        except Exception as e:
            error_msg = f"Error: {e}"
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            self.root.after(0, self._finish_postcal_cleanup)
    
    def _update_postcal_progress(self, progress, nse, kge, iteration):
        self.postcal_progress['value'] = progress
        self.postcal_iter_label.config(text=f"Iter: {iteration} | NSE: {nse:.4f} | KGE: {kge:.4f}")
    
    def _finish_postcal_cleanup(self):
        self.postcal_running = False
        self.postcal_start_btn.config(state=tk.NORMAL)
        self.postcal_stop_btn.config(state=tk.DISABLED)
    
    def _finish_glacier_autotune(self, params, metrics, status="Complete"):
        self.postcal_running = False
        self.postcal_start_btn.config(state=tk.NORMAL)
        self.postcal_stop_btn.config(state=tk.DISABLED)
        self.postcal_progress['value'] = 100
        self.postcal_iter_label.config(text=f"{status} ({len(self.postcal_iteration_history)} evaluations)")
        
        # Update sliders and entries
        for name, val in params.items():
            if name in self.postcal_param_vars:
                self.postcal_param_vars[name].set(val)
            if name in self.postcal_param_entries:
                self.postcal_param_entries[name].set(f"{val:.2f}")
        
        # Update metrics
        self.postcal_metrics.config(
            text=f"NSE={metrics['NSE']:.3f}  KGE={metrics['KGE']:.3f}  PBIAS={metrics['PBIAS']:.1f}%")
        
        # Show results with top 3 (Item 9)
        text = f"AUTO-TUNE: {status}\n{'='*50}\n\n"
        text += f"Total evaluations: {len(self.postcal_iteration_history)}\n\n"
        
        if self.postcal_best_results:
            text += "TOP 3 RESULTS:\n"
            for i, (obj, p, m) in enumerate(self.postcal_best_results[:3], 1):
                text += f"\n#{i} (Obj={obj:.4f}, NSE={m.get('NSE',0):.4f}, KGE={m.get('KGE',0):.4f}):\n"
                for k, v in p.items():
                    text += f"  {k}: {v:.4f}\n"
        
        text += f"\n{'='*50}\nFINAL PARAMETERS (applied):\n"
        for k, v in params.items():
            text += f"  {k}: {v:.6f}\n"
        if metrics:
            text += "\nMETRICS:\n"
            for k, v in metrics.items():
                text += f"  {k}: {v:.4f}\n"
        
        text += f"\n{'='*50}\n"
        text += "Use 'Show All History' to view all iterations.\n"
        text += "Use 'Export CSV' to save iteration history.\n"
        text += "Use 'Apply Optimized Params to Glacier Tab' to update glacier model."
        
        self.postcal_results_text.delete('1.0', tk.END)
        self.postcal_results_text.insert('1.0', text)
        self.log(f"Glacier auto-tune: {status}")
    
    def show_postcal_history(self):
        """Show all glacier postcal iteration history."""
        if not self.postcal_iteration_history:
            messagebox.showinfo("Info", "No iteration history available. Run auto-tune first.")
            return
        
        text = f"GLACIER POST-CAL ITERATION HISTORY\n{'='*60}\n\n"
        text += f"{'Iter':>6} {'Obj':>8} {'NSE':>8} {'KGE':>8} {'PBIAS':>8}\n"
        text += "-" * 42 + "\n"
        
        for h in self.postcal_iteration_history:
            text += f"{h['iteration']:>6d} {h['obj']:>8.4f} {h['NSE']:>8.4f} {h['KGE']:>8.4f} {h.get('PBIAS',0):>8.1f}\n"
        
        self.postcal_results_text.delete('1.0', tk.END)
        self.postcal_results_text.insert('1.0', text)
    
    def export_postcal_history_csv(self):
        """Export glacier postcal iteration history to CSV."""
        if not self.postcal_iteration_history:
            messagebox.showinfo("Info", "No iteration history available.")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                          filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                rows = []
                for h in self.postcal_iteration_history:
                    row = {
                        'iteration': h['iteration'],
                        'obj': h['obj'],
                        'NSE': h['NSE'],
                        'KGE': h['KGE'],
                        'PBIAS': h.get('PBIAS', 0)
                    }
                    row.update(h['params'])
                    rows.append(row)
                pd.DataFrame(rows).to_csv(fp, index=False)
                self.log(f"Exported glacier postcal history to {fp}")
                messagebox.showinfo("Success", f"Exported {len(rows)} iterations to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def apply_postcal_iteration(self):
        """Apply a specific iteration's parameters from postcal history."""
        if not self.postcal_iteration_history:
            messagebox.showinfo("Info", "No iteration history available.")
            return
        
        try:
            idx = int(self.postcal_apply_iter_var.get()) - 1
            if 0 <= idx < len(self.postcal_iteration_history):
                h = self.postcal_iteration_history[idx]
                for name, val in h['params'].items():
                    if name in self.postcal_param_vars:
                        self.postcal_param_vars[name].set(val)
                    if name in self.postcal_param_entries:
                        self.postcal_param_entries[name].set(f"{val:.2f}")
                self.log(f"Applied postcal iteration #{idx+1}: NSE={h['NSE']:.4f}, KGE={h['KGE']:.4f}")
            else:
                messagebox.showinfo("Info", f"Enter a number between 1 and {len(self.postcal_iteration_history)}")
        except ValueError:
            messagebox.showinfo("Info", "Enter a valid iteration number")
    
    def apply_postcal_to_glacier_tab(self):
        """Copy optimized postcal parameters to glacier tab sliders (Item 12)."""
        try:
            # Map postcal params to glacier tab params
            param_map = {
                'ddf_clean': 'ddf_clean',
                'ddf_debris': 'ddf_debris', 
                'lapse_rate': 'lapse_rate',
                't_melt': 't_melt',
                'ref_elev': 'ref_elev'
            }
            
            applied = []
            for postcal_name, glacier_name in param_map.items():
                val = self.postcal_param_vars[postcal_name].get()
                if hasattr(self, 'glacier_param_vars') and glacier_name in self.glacier_param_vars:
                    self.glacier_param_vars[glacier_name].set(val)
                    if hasattr(self, 'glacier_param_entries') and glacier_name in self.glacier_param_entries:
                        self.glacier_param_entries[glacier_name].set(f"{val:.2f}")
                    applied.append(f"{glacier_name}={val:.2f}")
            
            if applied:
                self.log(f"Applied postcal params to Glacier tab: {', '.join(applied)}")
                messagebox.showinfo("Success", f"Applied {len(applied)} parameters to Glacier tab.\n\nYou can now re-run the glacier model with optimized parameters.")
            else:
                messagebox.showwarning("Warning", "No matching parameters found in Glacier tab.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        for name, val in params.items():
            text += f"  {name}: {val:.4f}\n"
        text += f"\nMetrics:\n"
        for k, v in metrics.items():
            text += f"  {k}: {v:.4f}\n"
        
        self.postcal_results_text.delete('1.0', tk.END)
        self.postcal_results_text.insert('1.0', text)
        
        # Update glacier model params
        self.glacier_model.set_params(params)
        
        self.log(f"Glacier auto-tune complete: NSE={metrics['NSE']:.3f}")
    
    # =========================================================================
    # UNGAUGED CATCHMENT
    # =========================================================================
    
    def load_ungauged_shapefile(self):
        fp = filedialog.askopenfilename(filetypes=[("Shapefile", "*.shp")])
        if fp:
            info = extract_shapefile_info(fp)
            if info:
                self.ungauged_vars['area'].set(f"{info['area_km2']:.2f}")
                self.ungauged_vars['lat'].set(f"{info['latitude']:.4f}")
                self.ungauged_vars['name'].set(Path(fp).stem)
                self.log(f"Ungauged catchment: {info['area_km2']:.2f} km²")
    
    def load_ungauged_temp(self):
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.nc")])
        if fp:
            try:
                self.ungauged_temp = load_timeseries(fp)
                self.ungauged_status['temp'].config(text=f"✓ {len(self.ungauged_temp)} days", foreground='green')
                self.log(f"Ungauged temp: {len(self.ungauged_temp)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_ungauged_precip(self):
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.nc")])
        if fp:
            try:
                self.ungauged_precip = load_timeseries(fp)
                self.ungauged_status['precip'].config(text=f"✓ {len(self.ungauged_precip)} days", foreground='green')
                self.log(f"Ungauged precip: {len(self.ungauged_precip)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_ungauged_glacier(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                self.ungauged_glacier = load_csv_timeseries(fp)
                self.ungauged_status['glacier'].config(text=f"✓ {len(self.ungauged_glacier)} days", foreground='green')
                self.log(f"Ungauged glacier: {len(self.ungauged_glacier)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def load_ungauged_obs(self):
        fp = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if fp:
            try:
                self.ungauged_obs = load_csv_timeseries(fp)
                self.ungauged_status['obs'].config(text=f"✓ {len(self.ungauged_obs)} days", foreground='green')
                self.log(f"Ungauged obs: {len(self.ungauged_obs)} days")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def use_calibrated_for_ungauged(self):
        """Copy calibrated parameters to ungauged"""
        if self.hydro_model and self.hydro_model.params:
            for name, val in self.hydro_model.params.items():
                if name in self.ungauged_param_vars:
                    self.ungauged_param_vars[name].set(f"{val:.4f}")
            self.log("Using calibrated parameters for ungauged")
        else:
            messagebox.showinfo("Info", "Calibrate main model first")
    
    def use_history_for_ungauged(self):
        """Use parameters from iteration history for ungauged"""
        if not self.iteration_history:
            messagebox.showinfo("Info", "No iteration history available")
            return
        
        try:
            iter_num = int(self.ungauged_hist_var.get())
            found = None
            for h in self.iteration_history:
                if h['iteration'] == iter_num:
                    found = h
                    break
            
            if found:
                for name, val in found['params'].items():
                    if name in self.ungauged_param_vars:
                        self.ungauged_param_vars[name].set(f"{val:.4f}")
                self.log(f"Using iteration {iter_num} parameters for ungauged")
            else:
                messagebox.showerror("Error", f"Iteration {iter_num} not found")
        except ValueError:
            messagebox.showerror("Error", "Enter a valid iteration number")
    
    def run_ungauged_model(self):
        """Run model for ungauged catchment"""
        if self.ungauged_temp is None or self.ungauged_precip is None:
            messagebox.showerror("Error", "Load temperature and precipitation for ungauged catchment")
            return
        
        if self.ungauged_elev_bands is None:
            # Item 13: Warn but allow running without elevation bands
            if messagebox.askyesno("Warning", 
                "Elevation bands not loaded. The model will use a single band.\n"
                "This is not recommended for mountainous catchments.\n\nContinue anyway?"):
                self.ungauged_elev_bands = ElevationBands()
                self.ungauged_elev_bands.set_manual([3500])  # Single band default
            else:
                return
        
        try:
            area = float(self.ungauged_vars['area'].get())
            lat = float(self.ungauged_vars['lat'].get())
            
            start = pd.Timestamp(self.ungauged_start_var.get())
            end = pd.Timestamp(self.ungauged_end_var.get())
            dates = pd.date_range(start, end, freq='D')
            
            precip = self.ungauged_precip.reindex(dates).fillna(0).values
            temp = self.ungauged_temp.reindex(dates).interpolate().bfill().ffill().values
            
            # Glacier melt (optional) - convert m³/s to mm/day
            glacier_mm = np.zeros(len(dates))
            glacier_source = self.ungauged_glacier_source_var.get() if hasattr(self, 'ungauged_glacier_source_var') else 'none'
            
            if glacier_source == 'file' and self.ungauged_glacier is not None:
                # From uploaded file
                g_m3s = self.ungauged_glacier.reindex(dates).fillna(0).values
                glacier_mm = g_m3s * SECONDS_PER_DAY / (area * 1e6) * 1000
                self.log("Ungauged: using glacier melt from uploaded file")
            elif glacier_source == 'tab' and self.glacier_results is not None:
                # Item 14: From glacier tab results
                g = pd.Series(self.glacier_results['total_m3s'], index=self.glacier_results['dates']).reindex(dates).fillna(0).values
                glacier_mm = g * SECONDS_PER_DAY / (area * 1e6) * 1000
                self.log(f"Ungauged: using glacier melt from Glacier tab (mean={np.mean(glacier_mm):.3f} mm/d)")
            elif glacier_source == 'tab' and self.glacier_results is None:
                self.log("⚠ WARNING: Glacier Tab selected but no glacier results available. Run glacier model first.")
                messagebox.showwarning("Warning", "No glacier results in Glacier tab.\nRun the glacier model first, or upload a file.")
            
            # Get all parameters
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ks', 
                               'lapse_rate', 'ETmult', 'Imax', 'Ki', 'GWexch', 'LP']
            params = {}
            for name in all_param_names:
                if name in self.ungauged_param_vars:
                    params[name] = float(self.ungauged_param_vars[name].get())
                else:
                    # Defaults for any missing
                    if name == 'LP': params[name] = 0.7
                    elif name == 'Imax': params[name] = 2.0
                    elif name == 'GWexch': params[name] = 0.0
                    elif name == 'ETmult': params[name] = 1.0
                    elif name == 'Csub': params[name] = 0.0
                    elif name == 'Ki': params[name] = 0.05
            
            # Get catchment type
            ctype = self.catchment_type_var.get() if hasattr(self, 'catchment_type_var') else 'Universal'
            
            # Create model with elevation bands
            model = HKPHydroModel(area_km2=area, latitude=lat, catchment_type=ctype)
            model.elevation_bands = self.ungauged_elev_bands
            
            # Apply module settings
            if hasattr(self, 'use_snow_var'):
                model.use_snow = self.use_snow_var.get()
                model.use_sublimation = self.use_sublimation_var.get()
                model.use_interception = self.use_intercept_var.get()
                model.use_interflow = self.use_interflow_var.get()
                model.use_gw_exchange = self.use_gw_var.get()
            
            model.set_params(params)
            
            self.results_ungauged = model.run(precip, temp, dates, glacier_mm)
            self.results_ungauged['dates'] = dates
            
            # Store glacier for plotting
            if self.ungauged_glacier is not None:
                self.results_ungauged['glacier_m3s'] = self.ungauged_glacier.reindex(dates).fillna(0).values
            
            # Optional observed for comparison
            obs = None
            if self.ungauged_obs is not None:
                obs = self.ungauged_obs.reindex(dates).values
                self.results_ungauged['obs'] = obs
                
                warmup = 30
                m = calc_all_metrics(obs, self.results_ungauged['Q_sim_m3s'], warmup)
                self.ungauged_metrics_label.config(
                    text=f"NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}  PBIAS={m['PBIAS']:.1f}%  RMSE={m['RMSE']:.1f}")
            else:
                self.ungauged_metrics_label.config(text="No observed data for comparison")
            
            self.plot_ungauged()
            self.log(f"Ungauged model run: {start.date()} to {end.date()}")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def plot_ungauged(self):
        """Plot ungauged catchment results"""
        if self.results_ungauged is None:
            return
        
        dates = self.results_ungauged['dates']
        sim = self.results_ungauged['Q_sim_m3s']
        obs = self.results_ungauged.get('obs')
        
        self.ax_ungauged.clear()
        
        if obs is not None:
            self.ax_ungauged.plot(dates, obs, color='grey', lw=1.5, label='Observed')
        
        self.ax_ungauged.plot(dates, sim, color='red', lw=1, label='Simulated')
        
        # Add glacier if available
        if 'glacier_m3s' in self.results_ungauged:
            self.ax_ungauged.fill_between(dates, 0, self.results_ungauged['glacier_m3s'], 
                                         color='cyan', alpha=0.3, label='Glacier Input')
        
        name = self.ungauged_vars['name'].get() or "Ungauged"
        title = f"{name} - UNGAUGED SIMULATION"
        if obs is not None and np.sum(~np.isnan(obs)) > 10:
            m = calc_all_metrics(obs, sim, 30)
            title += f" | NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}"
        
        self.ax_ungauged.set_title(title, fontweight='bold')
        self.ax_ungauged.set_ylabel('Discharge (m³/s)')
        self.ax_ungauged.set_xlabel('Date')
        self.ax_ungauged.legend(loc='upper right')
        self.ax_ungauged.grid(True, alpha=0.3)
        
        self.fig_ungauged.tight_layout()
        self.canvas_ungauged.draw()
    
    def load_ungauged_elev_bands(self):
        """Load elevation bands for ungauged catchment"""
        fp = filedialog.askopenfilename(filetypes=[("All", "*.csv *.xlsx *.xls")])
        if fp:
            try:
                self.ungauged_elev_bands = ElevationBands()
                info = self.ungauged_elev_bands.load_from_file(fp)
                self.ungauged_status['elev_bands'].config(
                    text=f"✓ {info['n_bands']} bands, ref={info['ref_elev']:.0f}m", foreground='green')
                self.log(f"Ungauged elevation bands: {info['n_bands']}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def apply_manual_ungauged_elev_bands(self):
        """Item 13: Apply manually entered elevation bands."""
        try:
            centers_str = self.ungauged_elev_centers_var.get().strip()
            fracs_str = self.ungauged_elev_fracs_var.get().strip()
            
            centers = [float(x.strip()) for x in centers_str.split(',')]
            fracs = [float(x.strip()) for x in fracs_str.split(',')]
            
            if len(centers) != len(fracs):
                messagebox.showerror("Error", f"Number of centers ({len(centers)}) must match number of fractions ({len(fracs)})")
                return
            
            # Normalize fractions
            total = sum(fracs)
            if abs(total - 1.0) > 0.01:
                fracs = [f/total for f in fracs]
                self.log(f"Area fractions normalized (sum was {total:.3f})")
            
            self.ungauged_elev_bands = ElevationBands()
            self.ungauged_elev_bands.set_manual(centers, area_percents=[f*100 for f in fracs])
            
            n = len(centers)
            self.ungauged_status['elev_bands'].config(
                text=f"✓ {n} bands (manual), range={min(centers):.0f}-{max(centers):.0f}m", foreground='green')
            self.log(f"Manual elevation bands: {n} bands at {centers}")
        except Exception as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
    
    def export_ungauged_results(self):
        """Export ungauged model results to CSV"""
        if self.results_ungauged is None:
            messagebox.showinfo("Info", "Run ungauged model first")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                name = self.ungauged_vars['name'].get() or "ungauged"
                df = pd.DataFrame({
                    'Date': self.results_ungauged['dates'],
                    'Simulated_m3s': self.results_ungauged['Q_sim_m3s'],
                    'Simulated_mm': self.results_ungauged['Q_sim_mm'],
                    'Snow_mm': self.results_ungauged['snow'],
                    'Soil_mm': self.results_ungauged['soil'],
                    'Snowmelt_mm': self.results_ungauged['snowmelt'],
                    'Rain_mm': self.results_ungauged['rain'],
                    'ET_mm': self.results_ungauged['et'],
                    'Runoff_mm': self.results_ungauged['runoff'],
                    'Baseflow_mm': self.results_ungauged['baseflow']
                })
                
                if 'obs' in self.results_ungauged and self.results_ungauged['obs'] is not None:
                    df['Observed_m3s'] = self.results_ungauged['obs']
                
                if 'glacier_m3s' in self.results_ungauged:
                    df['Glacier_m3s'] = self.results_ungauged['glacier_m3s']
                
                df.to_csv(fp, index=False)
                self.log(f"Exported ungauged results to {fp}")
                messagebox.showinfo("Success", f"Exported to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def export_projection_results(self):
        """Export projection results to CSV"""
        if self.results_proj is None:
            messagebox.showinfo("Info", "Run projection first")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                df = pd.DataFrame({
                    'Date': self.results_proj['dates'],
                    'Simulated_m3s': self.results_proj['Q_sim_m3s'],
                    'Simulated_mm': self.results_proj['Q_sim_mm'],
                    'Snow_mm': self.results_proj['snow'],
                    'Soil_mm': self.results_proj['soil'],
                    'Snowmelt_mm': self.results_proj['snowmelt'],
                    'Rain_mm': self.results_proj['rain'],
                    'ET_mm': self.results_proj['et'],
                    'Runoff_mm': self.results_proj['runoff'],
                    'Baseflow_mm': self.results_proj['baseflow']
                })
                
                if 'obs' in self.results_proj and self.results_proj['obs'] is not None:
                    df['Observed_m3s'] = self.results_proj['obs']
                
                df.to_csv(fp, index=False)
                self.log(f"Exported projection results to {fp}")
                messagebox.showinfo("Success", f"Exported to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def export_glacier_results(self):
        """Export glacier model results to CSV"""
        if self.glacier_results is None:
            messagebox.showinfo("Info", "Run glacier model first")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                area = float(self.entry_vars['area'].get())
                total_m3s = np.array(self.glacier_results['total_m3s'])
                # Convert m³/s to mm/day for hydrological model input
                total_mm = total_m3s * SECONDS_PER_DAY / (area * 1e6) * 1000
                
                df = pd.DataFrame({
                    'Date': self.glacier_results['dates'],
                    'Clean_Ice_m3s': self.glacier_results['clean_m3s'],
                    'Debris_m3s': self.glacier_results['debris_m3s'],
                    'Total_m3s': self.glacier_results['total_m3s'],
                    'Total_mm_day': total_mm
                })
                df.to_csv(fp, index=False)
                
                period = f"{df['Date'].iloc[0]} to {df['Date'].iloc[-1]}"
                self.log(f"Exported glacier results ({len(df)} days, {period}) to {fp}")
                messagebox.showinfo("Success", f"Exported {len(df)} days to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def export_glacier_postcal_results(self):
        """Export glacier post-cal results to CSV"""
        if self.glacier_model is None or self.results_calib is None:
            messagebox.showinfo("Info", "Run glacier post-calibration first")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                dates = self.results_calib['dates']
                temp = self.results_calib['temp']
                
                # Get current params
                params = {}
                for k in self.postcal_param_vars:
                    try:
                        params[k] = float(self.postcal_param_entries[k].get())
                    except:
                        params[k] = self.postcal_param_vars[k].get()
                
                results = self.glacier_model.run(temp, dates, params)
                
                df = pd.DataFrame({
                    'Date': dates,
                    'Clean_Ice_m3s': results['clean_m3s'],
                    'Debris_m3s': results['debris_m3s'],
                    'Total_m3s': results['total_m3s']
                })
                df.to_csv(fp, index=False)
                self.log(f"Exported glacier post-cal results to {fp}")
                messagebox.showinfo("Success", f"Exported to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def apply_history_to_postcal(self):
        """Apply iteration history parameters to glacier post-cal (for lapse_rate)"""
        if not self.iteration_history:
            messagebox.showinfo("Info", "No iteration history available")
            return
        
        try:
            iter_num = int(self.postcal_hist_var.get())
            found = None
            for h in self.iteration_history:
                if h['iteration'] == iter_num:
                    found = h
                    break
            
            if found:
                # Only copy lapse_rate if it exists
                if 'lapse_rate' in found['params']:
                    val = found['params']['lapse_rate']
                    if 'lapse_rate' in self.postcal_param_vars:
                        self.postcal_param_vars['lapse_rate'].set(val)
                        self.postcal_param_entries['lapse_rate'].set(f"{val:.2f}")
                self.log(f"Applied lapse_rate from iteration {iter_num}")
            else:
                messagebox.showerror("Error", f"Iteration {iter_num} not found")
        except ValueError:
            messagebox.showerror("Error", "Enter a valid iteration number")
    
    def export_sensitivity_results(self):
        """Export sensitivity analysis results to CSV"""
        if self.sensitivity_results is None:
            messagebox.showinfo("Info", "Run sensitivity analysis first")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                all_data = []
                for name, r in self.sensitivity_results.items():
                    for i, val in enumerate(r['range']):
                        all_data.append({
                            'Parameter': name,
                            'Value': val,
                            'NSE': r['NSE'][i],
                            'KGE': r['KGE'][i],
                            'Optimal': r['optimal']
                        })
                
                df = pd.DataFrame(all_data)
                df.to_csv(fp, index=False)
                self.log(f"Exported sensitivity results to {fp}")
                messagebox.showinfo("Success", f"Exported to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    # =========================================================================
    # OPTIMIZATION
    # =========================================================================
    
    def stop_optimization(self):
        self.optimization_stop = True
        self.log("Stopping optimization...")
    
    def run_optimization(self):
        if self.temp_data is None or self.precip_data is None or self.obs_flow_calib is None:
            messagebox.showerror("Error", "Load all data first")
            return
        
        if self.optimization_running:
            return
        
        self.optimization_running = True
        self.optimization_stop = False
        self.best_results = []
        self.opt_start_btn.config(state=tk.DISABLED)
        self.opt_stop_btn.config(state=tk.NORMAL)
        self.opt_status.config(text="Starting...")
        self.opt_results_text.delete('1.0', tk.END)
        self.opt_progress['value'] = 0
        
        threading.Thread(target=self._optimization_thread, daemon=True).start()
    
    def _optimization_thread(self):
        try:
            area = float(self.entry_vars['area'].get())
            lat = float(self.entry_vars['lat'].get())
            warmup = int(self.warmup_var.get())
            maxiter = int(self.maxiter_var.get())
            popsize = int(self.popsize_var.get())
            tol = float(self.tol_var.get())
            method = self.opt_method_var.get()
            auto_stop = self.auto_stop_var.get()
            no_improve_limit = int(self.no_improve_limit_var.get())
            min_improve = float(self.min_improve_var.get())
            spinup_years = int(self.spinup_var.get()) if hasattr(self, 'spinup_var') else 2
            
            weights = {k: float(v.get()) for k, v in self.weight_vars.items()}
            
            start = pd.Timestamp(self.calib_start_var.get())
            end = pd.Timestamp(self.calib_end_var.get())
            
            with_gl = self.glacier_calib_var.get() == 'with'
            dates, precip, temp, glacier_mm = self.prepare_data(start, end, with_glacier=with_gl)
            obs = self.obs_flow_calib.reindex(dates).values
            
            model = HKPHydroModel(area_km2=area, latitude=lat)
            model.elevation_bands = self.elevation_bands
            
            # Apply module settings
            if hasattr(self, 'use_snow_var'):
                model.use_snow = self.use_snow_var.get()
                model.use_sublimation = self.use_sublimation_var.get()
                model.use_interception = self.use_intercept_var.get()
                model.use_interflow = self.use_interflow_var.get()
                model.use_gw_exchange = self.use_gw_var.get()
            
            # Prepare validation data (only for final evaluation after optimization)
            has_valid = (self.obs_flow_valid is not None and 
                        self.temp_data is not None and self.precip_data is not None)
            val_dates = val_precip = val_temp = val_glacier_mm = val_obs = None
            if has_valid:
                try:
                    val_start = pd.Timestamp(self.valid_start_var.get())
                    val_end = pd.Timestamp(self.valid_end_var.get())
                    val_dates, val_precip, val_temp, val_glacier_mm = self.prepare_data(
                        val_start, val_end, with_glacier=with_gl)
                    val_obs = self.obs_flow_valid.reindex(val_dates).values
                except Exception:
                    has_valid = False
            bounds = []
            fixed_params = {}
            param_indices = []
            
            # All 14 parameter names
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ks', 
                               'lapse_rate', 'ETmult', 'Imax', 'Ki', 'GWexch', 'LP']
            
            for i, name in enumerate(all_param_names):
                if name in self.param_optimize_vars and self.param_optimize_vars[name].get():
                    mn = float(self.param_min_vars[name].get())
                    mx = float(self.param_max_vars[name].get())
                    bounds.append((mn, mx))
                    param_indices.append(i)
                elif name in self.param_fixed_vars:
                    fixed_params[name] = float(self.param_fixed_vars[name].get())
                else:
                    # Default values for missing parameters
                    if name == 'LP':
                        fixed_params[name] = 0.7
                    elif name == 'Imax':
                        fixed_params[name] = 2.0
                    elif name == 'GWexch':
                        fixed_params[name] = 0.0
                    elif name == 'ETmult':
                        fixed_params[name] = 1.0
                    elif name == 'Csub':
                        fixed_params[name] = 0.0
                    elif name == 'Ki':
                        fixed_params[name] = 0.05
            
            if len(bounds) == 0:
                self.root.after(0, lambda: messagebox.showerror("Error", "Select at least one parameter"))
                self._finish_optimization_cleanup()
                return
            
            self.iteration_count = 0
            self.best_obj = float('inf')
            self.no_improve_count = 0
            self.last_update = time.time()
            self.iteration_history = []  # Store ALL iterations
            self.best_results = []  # Top 3
            
            n_params = len(bounds)
            total_evals = maxiter * popsize * n_params  # Approximate
            
            stop_reason = [None]
            
            def objective(x):
                if self.optimization_stop:
                    stop_reason[0] = "User stopped"
                    raise StopIteration("User stopped")
                
                # Build params from all parameters
                params = {}
                opt_idx = 0
                for name in all_param_names:
                    if name in fixed_params:
                        params[name] = fixed_params[name]
                    else:
                        params[name] = x[opt_idx]
                        opt_idx += 1
                
                try:
                    # Use spinup for proper state initialization (critical for CSV data)
                    if spinup_years > 0:
                        r = model.run_with_spinup(precip, temp, dates, glacier_mm, params, 
                                                 spinup_years=spinup_years, return_components=False)
                    else:
                        r = model.run(precip, temp, dates, glacier_mm, params, return_components=False)
                    sim = r['Q_sim_m3s']
                    o, s = obs[warmup:], sim[warmup:]
                    mask = ~(np.isnan(o) | np.isnan(s))
                    if mask.sum() < 10:
                        return float(1e6)
                    
                    nse = float(calc_nse(o[mask], s[mask]))
                    nse_log = float(calc_nse_log(o[mask], s[mask]))
                    kge = float(calc_kge(o[mask], s[mask]))
                    pbias = float(abs(calc_pbias(o[mask], s[mask])))
                    
                    obj = float(weights['NSE']*(1-nse) + weights['NSE_log']*(1-nse_log) + 
                           weights['KGE']*(1-kge) + weights['PBIAS']*(pbias/100))
                    
                    # NOTE: Validation is NOT run per iteration (for speed).
                    # It is computed once after optimization completes.
                    val_nse = val_nse_log = val_kge = val_pbias = float('nan')
                    
                    self.iteration_count += 1
                    
                    # Store in iteration history (calibration only per iteration)
                    self.iteration_history.append({
                        'iteration': self.iteration_count,
                        'params': params.copy(),
                        'obj': obj,
                        'NSE': nse, 'NSE_log': nse_log, 'KGE': kge, 'PBIAS': pbias,
                        'val_NSE': float('nan'), 'val_NSE_log': float('nan'),
                        'val_KGE': float('nan'), 'val_PBIAS': float('nan')
                    })
                    
                    # Track best 3 results
                    if len(self.best_results) < 3 or obj < self.best_results[-1][0]:
                        self.best_results.append((obj, params.copy(), 
                            {'NSE': nse, 'KGE': kge, 'NSE_log': nse_log, 'PBIAS': pbias,
                             'val_NSE': float('nan'), 'val_KGE': float('nan'),
                             'val_NSE_log': float('nan'), 'val_PBIAS': float('nan')}))
                        self.best_results.sort(key=lambda x: x[0])
                        self.best_results = self.best_results[:3]
                    
                    # Check improvement
                    if obj < self.best_obj - min_improve:
                        self.best_obj = obj
                        self.no_improve_count = 0
                    else:
                        self.no_improve_count += 1
                    
                    # Auto-stop when converged
                    if auto_stop and self.no_improve_count >= no_improve_limit:
                        stop_reason[0] = f"Converged (no improvement for {no_improve_limit} iterations)"
                        raise StopIteration(stop_reason[0])
                    
                    # Update progress (calibration metrics only - validation runs after optimization)
                    if time.time() - self.last_update > 0.3:
                        self.last_update = time.time()
                        progress = min(95, self.iteration_count / max(1, total_evals) * 100)
                        self.root.after(0, lambda i=self.iteration_count, n=nse, k=kge, 
                                       p=progress, ni=self.no_improve_count: 
                                       self._update_opt_progress(i, n, k, p, ni))
                    
                    if not np.isfinite(obj):
                        return float(1e6)
                    return float(obj)
                except StopIteration:
                    raise
                except:
                    return float(1e6)
            
            self.root.after(0, lambda: self.opt_status.config(text=f"Running {method}..."))
            
            try:
                if method == "DE":
                    result = differential_evolution(objective, bounds, maxiter=maxiter, 
                                                   popsize=popsize, tol=tol, seed=42, polish=True)
                    x_opt = result.x
                elif method == "PSO":
                    optimizer = ParticleSwarmOptimizer(objective, bounds, n_particles=popsize, 
                                                       max_iter=maxiter, seed=42)
                    result = optimizer.optimize()
                    x_opt = result['x']
                elif method == "SCEUA":
                    optimizer = ShuffledComplexEvolution(objective, bounds, n_complexes=4, 
                                                        max_iter=maxiter, seed=42)
                    result = optimizer.optimize()
                    x_opt = result['x']
                elif method == "ADE":
                    optimizer = AdaptiveDifferentialEvolution(objective, bounds, popsize=popsize, 
                                                              max_iter=maxiter, seed=42)
                    result = optimizer.optimize()
                    x_opt = result['x']
                elif method == "BH":
                    initial = [(b[0]+b[1])/2 for b in bounds]
                    result = basinhopping(objective, initial, 
                                         minimizer_kwargs={"method": "L-BFGS-B", "bounds": bounds},
                                         niter=maxiter, seed=42)
                    x_opt = result.x
                elif method == "LBFGSB":
                    initial = [(b[0]+b[1])/2 for b in bounds]
                    result = minimize(objective, initial, method='L-BFGS-B', bounds=bounds)
                    x_opt = result.x
                
                stop_reason[0] = "Complete"
                    
            except StopIteration:
                # Return best result so far
                if self.best_results:
                    _, best_params, best_metrics = self.best_results[0]
                    reason = stop_reason[0] or "Stopped"
                    self.root.after(0, lambda p=best_params, m=best_metrics, r=reason: 
                                   self._finish_optimization(p, m, r))
                else:
                    reason = stop_reason[0] or "Stopped"
                    self.root.after(0, lambda r=reason: self._finish_optimization(None, None, r))
                return
            
            # Build final params using all 14 parameter names
            opt_params = {}
            opt_idx = 0
            for i, name in enumerate(all_param_names):
                if name in fixed_params:
                    opt_params[name] = fixed_params[name]
                else:
                    opt_params[name] = x_opt[opt_idx]
                    opt_idx += 1
            
            model.set_params(opt_params)
            final = model.run(precip, temp, dates, glacier_mm)
            metrics = calc_all_metrics(obs, final['Q_sim_m3s'], warmup)
            model.calibration_metrics = metrics
            
            # Run final validation
            val_metrics = {}
            if has_valid:
                try:
                    if spinup_years > 0:
                        final_val = model.run_with_spinup(val_precip, val_temp, val_dates,
                                                          val_glacier_mm, opt_params, spinup_years=spinup_years)
                    else:
                        final_val = model.run(val_precip, val_temp, val_dates, val_glacier_mm, opt_params)
                    val_metrics = calc_all_metrics(val_obs, final_val['Q_sim_m3s'], warmup)
                    model.validation_metrics = val_metrics
                except Exception:
                    pass
            
            self.hydro_model = model
            reason = stop_reason[0] or "Complete"
            self.root.after(0, lambda p=opt_params, m=metrics, vm=val_metrics, r=reason: 
                           self._finish_optimization(p, m, r, vm))
            
        except Exception as e:
            error_msg = f"Error: {e}"
            self.root.after(0, lambda msg=error_msg: self._finish_optimization(None, None, msg))
    
    def _update_opt_progress(self, iteration, nse, kge, progress, no_improve, val_nse=None, val_kge=None):
        self.opt_progress['value'] = progress
        txt = f"Iter: {iteration} | Cal NSE: {nse:.4f} KGE: {kge:.4f}"
        txt += f" | No-improve: {no_improve} | (Validation runs after optimization)"
        self.opt_iter_label.config(text=txt)
    
    def _finish_optimization(self, params, metrics, status, val_metrics=None):
        self.optimization_running = False
        self.opt_start_btn.config(state=tk.NORMAL)
        self.opt_stop_btn.config(state=tk.DISABLED)
        self.opt_progress['value'] = 100 if params else self.opt_progress['value']
        self.opt_status.config(text=status)
        
        text = f"OPTIMIZATION: {status}\n{'='*60}\n\n"
        text += f"Total iterations: {self.iteration_count}\n"
        text += f"Iteration history saved: {len(self.iteration_history)} entries\n\n"
        
        # Show best 3 results (with validation)
        if self.best_results:
            text += "TOP 3 RESULTS:\n"
            for i, (obj, p, m) in enumerate(self.best_results[:3], 1):
                cal_txt = f"Cal NSE={m.get('NSE', 0):.4f}, KGE={m.get('KGE', 0):.4f}"
                v_nse = m.get('val_NSE', float('nan'))
                v_kge = m.get('val_KGE', float('nan'))
                val_txt = ""
                if isinstance(v_nse, float) and not np.isnan(v_nse):
                    val_txt = f" | Val NSE={v_nse:.4f}, KGE={v_kge:.4f}"
                text += f"\n#{i} (Obj={obj:.4f}, {cal_txt}{val_txt}):\n"
                for k, v in p.items():
                    fixed = "(fixed)" if not self.param_optimize_vars.get(k, tk.BooleanVar()).get() else ""
                    text += f"  {k}: {v:.4f} {fixed}\n"
        
        if params:
            text += f"\n{'='*60}\nFINAL PARAMETERS (applied):\n"
            for k, v in params.items():
                text += f"  {k}: {v:.6f}\n"
            if metrics:
                text += "\nCALIBRATION METRICS:\n"
                for k, v in metrics.items():
                    text += f"  {k}: {v:.4f}\n"
            if val_metrics:
                text += "\nVALIDATION METRICS:\n"
                for k, v in val_metrics.items():
                    text += f"  {k}: {v:.4f}\n"
        
        text += f"\n{'='*60}\n"
        text += "Use 'Show History' to view all iterations (Calib + Valid).\n"
        text += "Enter iteration # and click 'Apply' to use specific parameters."
        
        self.opt_results_text.delete('1.0', tk.END)
        self.opt_results_text.insert('1.0', text)
        
        if params:
            # Store a PERMANENT copy of optimized params (never overwritten by manual runs)
            self.stored_optimized_params = params.copy()
            
            for k, v in params.items():
                if k in self.param_vars:
                    self.param_vars[k].set(v)
                    self.param_entries[k].set(f"{v:.4f}")
            
            if metrics:
                for k, v in metrics.items():
                    if k in self.metric_labels:
                        txt = f"{v:.1f}%" if k == 'PBIAS' else f"{v:.3f}" if k != 'RMSE' else f"{v:.1f}"
                        self.metric_labels[k].config(text=txt)
            
            self.log(f"Optimization: {status}")
            # Run model to show plots
            try:
                self.run_model()
            except:
                pass
        else:
            self.log(f"Optimization: {status} (no valid parameters found)")
    
    def _finish_optimization_cleanup(self):
        """Cleanup after optimization error"""
        self.optimization_running = False
        self.opt_start_btn.config(state=tk.NORMAL)
        self.opt_stop_btn.config(state=tk.DISABLED)
    
    def show_iteration_history(self):
        """Show all iteration history with calibration + validation metrics"""
        if not self.iteration_history:
            messagebox.showinfo("Info", "No iteration history available. Run optimization first.")
            return
        
        win = tk.Toplevel(self.root)
        win.title("Iteration History (Calibration + Validation)")
        win.geometry("1200x650")
        
        has_val = any(not np.isnan(h.get('val_NSE', float('nan'))) for h in self.iteration_history)
        
        info_frame = ttk.Frame(win)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"Total iterations: {len(self.iteration_history)}  |  "
                  f"Validation: {'Yes' if has_val else 'No (no validation data during optimization)'}", 
                 font=('Helvetica', 10, 'bold')).pack(anchor='w')
        
        text = ScrolledText(win, font=('Consolas', 9))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        if has_val:
            header = (f"{'Iter':>6} {'Obj':>10} \u2502 {'Cal_NSE':>8} {'Cal_logN':>8} {'Cal_KGE':>8} "
                      f"{'Cal_PB':>8} \u2502 {'Val_NSE':>8} {'Val_logN':>8} {'Val_KGE':>8} {'Val_PB':>8}")
            text.insert(tk.END, header + "\n")
            text.insert(tk.END, "-" * 105 + "\n")
        else:
            header = f"{'Iter':>6} {'Obj':>10} {'NSE':>8} {'NSE_log':>8} {'KGE':>8} {'PBIAS':>8}"
            text.insert(tk.END, header + "\n")
            text.insert(tk.END, "-" * 60 + "\n")
        
        sorted_hist = sorted(self.iteration_history, key=lambda x: x['obj'])
        
        for h in sorted_hist:
            if has_val:
                vn = h.get('val_NSE', float('nan'))
                vnl = h.get('val_NSE_log', float('nan'))
                vk = h.get('val_KGE', float('nan'))
                vp = h.get('val_PBIAS', float('nan'))
                vn_s = f"{vn:>8.4f}" if not np.isnan(vn) else f"{'N/A':>8}"
                vnl_s = f"{vnl:>8.4f}" if not np.isnan(vnl) else f"{'N/A':>8}"
                vk_s = f"{vk:>8.4f}" if not np.isnan(vk) else f"{'N/A':>8}"
                vp_s = f"{vp:>8.2f}" if not np.isnan(vp) else f"{'N/A':>8}"
                line = (f"{h['iteration']:>6} {h['obj']:>10.4f} \u2502 {h['NSE']:>8.4f} {h['NSE_log']:>8.4f} "
                        f"{h['KGE']:>8.4f} {h['PBIAS']:>8.2f} \u2502 {vn_s} {vnl_s} {vk_s} {vp_s}\n")
            else:
                line = (f"{h['iteration']:>6} {h['obj']:>10.4f} {h['NSE']:>8.4f} "
                        f"{h['NSE_log']:>8.4f} {h['KGE']:>8.4f} {h['PBIAS']:>8.2f}\n")
            text.insert(tk.END, line)
        
        text.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Export to CSV", 
                  command=self.export_iteration_history).pack(side=tk.LEFT, padx=5)
    
    def apply_history_iteration(self):
        """Apply parameters from a specific iteration number"""
        if not self.iteration_history:
            messagebox.showinfo("Info", "No iteration history available")
            return
        
        try:
            iter_num = int(self.hist_iter_var.get())
            
            # Find the iteration
            found = None
            for h in self.iteration_history:
                if h['iteration'] == iter_num:
                    found = h
                    break
            
            if found is None:
                messagebox.showerror("Error", f"Iteration {iter_num} not found")
                return
            
            params = found['params']
            
            for k, v in params.items():
                if k in self.param_vars:
                    self.param_vars[k].set(v)
                    self.param_entries[k].set(f"{v:.4f}")
            
            msg = f"Applied iteration {iter_num}: Cal NSE={found['NSE']:.4f}, KGE={found['KGE']:.4f}"
            val_nse = found.get('val_NSE', float('nan'))
            if isinstance(val_nse, float) and not np.isnan(val_nse):
                msg += f" | Val NSE={val_nse:.4f}, KGE={found.get('val_KGE', 0):.4f}"
            self.log(msg)
            self.run_model()
            
        except ValueError:
            messagebox.showerror("Error", "Enter a valid iteration number")
    
    def export_iteration_history(self):
        """Export iteration history to CSV with calibration + validation metrics"""
        if not self.iteration_history:
            messagebox.showinfo("Info", "No iteration history to export")
            return
        
        fp = filedialog.asksaveasfilename(defaultextension=".csv", 
                                         filetypes=[("CSV files", "*.csv")])
        if fp:
            try:
                rows = []
                for h in self.iteration_history:
                    row = {'iteration': h['iteration'], 'obj': h['obj'], 
                           'cal_NSE': h['NSE'], 'cal_NSE_log': h['NSE_log'], 
                           'cal_KGE': h['KGE'], 'cal_PBIAS': h['PBIAS'],
                           'val_NSE': h.get('val_NSE', ''),
                           'val_NSE_log': h.get('val_NSE_log', ''),
                           'val_KGE': h.get('val_KGE', ''),
                           'val_PBIAS': h.get('val_PBIAS', '')}
                    # Clean NaN to empty for CSV
                    for k in ['val_NSE', 'val_NSE_log', 'val_KGE', 'val_PBIAS']:
                        if isinstance(row[k], float) and np.isnan(row[k]):
                            row[k] = ''
                    row.update(h['params'])
                    rows.append(row)
                
                df = pd.DataFrame(rows)
                df.to_csv(fp, index=False)
                self.log(f"Exported iteration history to {fp}")
                messagebox.showinfo("Success", f"Exported {len(rows)} iterations to {fp}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    # =========================================================================
    # SENSITIVITY
    # =========================================================================
    
    def run_sensitivity(self):
        if self.hydro_model is None:
            self.hydro_model = HKPHydroModel(
                area_km2=float(self.entry_vars['area'].get()),
                latitude=float(self.entry_vars['lat'].get())
            )
            self.hydro_model.elevation_bands = self.elevation_bands
            
            # Get all parameters
            all_param_names = ['Tt', 'Cm', 'Csub', 'FC', 'beta', 'alpha', 'Kq', 'Ks', 
                               'lapse_rate', 'ETmult', 'Imax', 'Ki', 'GWexch', 'LP']
            params = {}
            for name in all_param_names:
                if name in self.param_vars:
                    params[name] = self.param_vars[name].get()
                else:
                    # Defaults for any missing
                    if name == 'LP': params[name] = 0.7
                    elif name == 'Imax': params[name] = 2.0
                    elif name == 'GWexch': params[name] = 0.0
                    elif name == 'ETmult': params[name] = 1.0
                    elif name == 'Csub': params[name] = 0.0
                    elif name == 'Ki': params[name] = 0.05
            self.hydro_model.set_params(params)
        
        self.sens_results_text.delete('1.0', tk.END)
        threading.Thread(target=self._sens_thread, daemon=True).start()
    
    def _sens_thread(self):
        try:
            n = int(self.sens_n_var.get())
            warmup = int(self.warmup_var.get())
            
            start = pd.Timestamp(self.calib_start_var.get())
            end = pd.Timestamp(self.calib_end_var.get())
            with_gl = self.glacier_calib_var.get() == 'with'
            dates, precip, temp, glacier_mm = self.prepare_data(start, end, with_glacier=with_gl)
            obs = self.obs_flow_calib.reindex(dates).values
            
            # All parameters with literature-based bounds for sensitivity analysis
            all_params_sens = [
                ('Tt',         (-3.0,   3.0)),
                ('Cm',         (0.5,   12.0)),
                ('Csub',       (0.0,    1.0)),
                ('FC',         (10.0, 600.0)),
                ('beta',       (0.5,    6.0)),
                ('alpha',      (0.01,  0.99)),
                ('Kq',         (0.01,  0.999)),
                ('Ks',         (0.0001, 0.1)),
                ('lapse_rate', (4.0,   10.0)),
                ('ETmult',     (0.3,    2.0)),
                ('Imax',       (0.0,    6.0)),
                ('Ki',         (0.0001, 0.8)),
                ('GWexch',     (-3.0,   3.0)),
                ('LP',         (0.1,    1.0))
            ]
            
            # Filter to only selected parameters
            params_to_analyze = []
            if hasattr(self, 'sens_param_vars'):
                for name, bounds in all_params_sens:
                    if name in self.sens_param_vars and self.sens_param_vars[name].get():
                        params_to_analyze.append((name, bounds))
            else:
                # If no checkboxes, analyze all
                params_to_analyze = all_params_sens
            
            if len(params_to_analyze) == 0:
                self.root.after(0, lambda: messagebox.showwarning("Warning", "Select at least one parameter"))
                return
            
            base_params = self.hydro_model.params.copy()
            results = {}
            
            for idx, (name, bounds) in enumerate(params_to_analyze):
                rng = np.linspace(bounds[0], bounds[1], n)
                
                nse_vals, kge_vals = [], []
                for val in rng:
                    params = base_params.copy()
                    params[name] = val
                    try:
                        r = self.hydro_model.run(precip, temp, dates, glacier_mm, params, False)
                        nse_vals.append(calc_nse(obs[warmup:], r['Q_sim_m3s'][warmup:]))
                        kge_vals.append(calc_kge(obs[warmup:], r['Q_sim_m3s'][warmup:]))
                    except:
                        nse_vals.append(np.nan)
                        kge_vals.append(np.nan)
                
                results[name] = {
                    'range': rng, 
                    'NSE': np.array(nse_vals), 
                    'KGE': np.array(kge_vals),
                    'optimal': base_params.get(name, (bounds[0]+bounds[1])/2)
                }
                
                progress = (idx + 1) / len(params_to_analyze) * 100
                self.root.after(0, lambda p=progress: self.sens_progress.configure(value=p))
            
            self.sensitivity_results = results
            self.root.after(0, self._update_sens_ui)
            
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
    
    def _update_sens_ui(self):
        indices = {n: np.nanmax(r['NSE'])-np.nanmin(r['NSE']) for n, r in self.sensitivity_results.items()}
        sorted_p = sorted(indices.items(), key=lambda x: x[1], reverse=True)
        
        text = "SENSITIVITY RANKING\n" + "="*40 + "\n\n"
        for rank, (name, sens) in enumerate(sorted_p, 1):
            text += f"{rank}. {name:12s}: {sens:.4f}\n"
        
        self.sens_results_text.delete('1.0', tk.END)
        self.sens_results_text.insert('1.0', text)
        self.plot_sensitivity()
    
    # =========================================================================
    # PLOTTING - RED SIMULATED LINES
    # =========================================================================
    
    def plot_calibration(self):
        if self.results_calib is None:
            return
        
        dates = self.results_calib['dates']
        obs = self.results_calib.get('obs')
        sim = self.results_calib['Q_sim_m3s']
        warmup = int(self.warmup_var.get())
        
        self.ax1.clear()
        if obs is not None:
            self.ax1.plot(dates, obs, color='grey', lw=1.5, label='Observed')
        self.ax1.plot(dates, sim, color='red', lw=1, label='Simulated')  # RED
        
        if warmup > 0 and warmup < len(dates):
            self.ax1.axvline(dates[warmup], color='blue', ls=':', alpha=0.5, label='Warmup')
        
        if obs is not None:
            m = calc_all_metrics(obs, sim, warmup)
            self.ax1.set_title(f"CALIBRATION: NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}  PBIAS={m['PBIAS']:.1f}%",
                             fontweight='bold')
        else:
            self.ax1.set_title("CALIBRATION", fontweight='bold')
        
        self.ax1.set_ylabel('Discharge (m³/s)')
        self.ax1.legend(loc='upper right')
        self.ax1.grid(True, alpha=0.3)
        self.fig1.tight_layout()
        self.canvas1.draw()
    
    def plot_validation(self):
        if self.results_valid is None:
            return
        
        dates = self.results_valid['dates']
        obs = self.results_valid.get('obs')
        sim = self.results_valid['Q_sim_m3s']
        warmup = int(self.warmup_var.get())
        
        self.ax2.clear()
        if obs is not None:
            self.ax2.plot(dates, obs, color='grey', lw=1.5, label='Observed')
        self.ax2.plot(dates, sim, color='red', lw=1, label='Simulated')  # RED
        
        if obs is not None:
            m = calc_all_metrics(obs, sim, warmup)
            self.ax2.set_title(f"VALIDATION: NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}  PBIAS={m['PBIAS']:.1f}%",
                             fontweight='bold')
        else:
            self.ax2.set_title("VALIDATION", fontweight='bold')
        
        self.ax2.set_ylabel('Discharge (m³/s)')
        self.ax2.legend(loc='upper right')
        self.ax2.grid(True, alpha=0.3)
        self.fig2.tight_layout()
        self.canvas2.draw()
    
    def plot_projection(self):
        if self.results_proj is None:
            return
        
        dates = self.results_proj['dates']
        obs = self.results_proj.get('obs')
        sim = self.results_proj['Q_sim_m3s']
        
        self.ax4.clear()
        if obs is not None:
            self.ax4.plot(dates, obs, color='grey', lw=1.5, label='Observed')
        self.ax4.plot(dates, sim, color='red', lw=1, label='Simulated')  # RED
        
        title = "PROJECTION"
        if obs is not None and np.sum(~np.isnan(obs)) > 10:
            m = calc_all_metrics(obs, sim, 30)
            title += f": NSE={m['NSE']:.3f}  KGE={m['KGE']:.3f}"
        
        self.ax4.set_title(title, fontweight='bold')
        self.ax4.set_ylabel('Discharge (m³/s)')
        self.ax4.legend(loc='upper right')
        self.ax4.grid(True, alpha=0.3)
        self.fig4.tight_layout()
        self.canvas4.draw()
    
    def plot_comprehensive(self):
        if self.results_calib is None:
            return
        
        dates = self.results_calib['dates']
        obs = self.results_calib.get('obs')
        sim = self.results_calib['Q_sim_m3s']
        
        for ax in self.axes3:
            ax.clear()
        
        self.axes3[0].bar(dates, self.results_calib['precip'], width=1, color='blue', alpha=0.7)
        self.axes3[0].set_ylabel('Precip (mm)')
        self.axes3[0].invert_yaxis()
        self.axes3[0].set_title(f"{self.entry_vars['catchment_name'].get()} - Comprehensive", fontweight='bold')
        
        ax_t = self.axes3[1]
        ax_s = ax_t.twinx()
        
        ax_t.plot(dates, self.results_calib['temp'], color='red', lw=0.8)
        ax_t.set_ylabel('Temp (°C)', color='red')
        ax_t.tick_params(axis='y', labelcolor='red')
        ax_t.yaxis.set_major_locator(MaxNLocator(nbins=5))
        
        snow_max = np.max(self.results_calib['snow'])
        ax_s.fill_between(dates, 0, self.results_calib['snow'], color='lightblue', alpha=0.7, label='Model SWE')
        
        # SWE observed overlay
        if hasattr(self, 'swe_obs_data') and self.swe_obs_data is not None:
            swe_aligned = self.swe_obs_data.reindex(dates)
            if swe_aligned.notna().sum() > 0:
                ax_s.plot(dates, swe_aligned.values, color='darkblue', lw=1.2, 
                         ls='--', marker='.', markersize=2, label='Observed SWE')
                snow_max = max(snow_max, np.nanmax(swe_aligned.dropna().values)) if swe_aligned.notna().sum() > 0 else snow_max
            ax_s.legend(fontsize=7, loc='upper right')
        
        ax_s.set_ylabel('SWE (mm)', color='blue')
        ax_s.tick_params(axis='y', labelcolor='blue')
        
        # Set SWE y-axis with nice round numbers for better readability
        if snow_max > 0:
            # Calculate nice tick interval (round up to nearest 50, 100, 200, 500, etc.)
            magnitude = 10 ** np.floor(np.log10(snow_max))
            nice_interval = magnitude
            if snow_max / magnitude > 5:
                nice_interval = magnitude * 2
            elif snow_max / magnitude > 2:
                nice_interval = magnitude
            else:
                nice_interval = magnitude / 2
            
            nice_interval = max(50, nice_interval)  # Minimum 50 mm interval
            max_tick = int(np.ceil(snow_max / nice_interval) * nice_interval)
            ax_s.set_ylim(0, max_tick)
            ax_s.yaxis.set_major_locator(plt.MultipleLocator(nice_interval))
        else:
            ax_s.set_ylim(0, 100)
            ax_s.yaxis.set_major_locator(plt.MultipleLocator(20))
        
        FC = self.param_vars['FC'].get()
        self.axes3[2].fill_between(dates, 0, self.results_calib['soil'], color='brown', alpha=0.5)
        self.axes3[2].axhline(FC, color='brown', ls='--', alpha=0.5, label=f'FC={FC:.0f}')
        self.axes3[2].set_ylabel('Soil (mm)')
        self.axes3[2].legend(loc='upper right', fontsize=8)
        
        if obs is not None:
            self.axes3[3].plot(dates, obs, color='grey', lw=1.5, label='Observed')
        self.axes3[3].plot(dates, sim, color='red', lw=1, label='Simulated')  # RED
        self.axes3[3].set_ylabel('Q (m³/s)')
        self.axes3[3].set_xlabel('Date')
        self.axes3[3].legend(loc='upper right')
        
        self.fig3.tight_layout()
        self.canvas3.draw()
    
    def plot_comprehensive_validation(self):
        """Plot comprehensive view for VALIDATION period."""
        if self.results_valid is None:
            return
        
        dates = self.results_valid['dates']
        obs = self.results_valid.get('obs')
        sim = self.results_valid['Q_sim_m3s']
        precip = self.results_valid.get('precip')
        temp_data = self.results_valid.get('temp')
        snow = self.results_valid.get('snow')
        soil = self.results_valid.get('soil')
        
        for ax in self.axes3v:
            ax.clear()
        
        # Panel 1: Precipitation
        if precip is not None:
            self.axes3v[0].bar(dates, precip, width=1, color='blue', alpha=0.7)
        self.axes3v[0].set_ylabel('Precip (mm)')
        self.axes3v[0].invert_yaxis()
        self.axes3v[0].set_title(f"{self.entry_vars['catchment_name'].get()} - Comprehensive (Validation)", fontweight='bold')
        
        # Panel 2: Temperature + SWE
        ax_t = self.axes3v[1]
        ax_s = ax_t.twinx()
        
        if temp_data is not None:
            ax_t.plot(dates, temp_data, color='red', lw=0.8)
        ax_t.set_ylabel('Temp (°C)', color='red')
        ax_t.tick_params(axis='y', labelcolor='red')
        ax_t.yaxis.set_major_locator(MaxNLocator(nbins=5))
        
        if snow is not None:
            snow_max = np.max(snow) if np.max(snow) > 0 else 100
            ax_s.fill_between(dates, 0, snow, color='lightblue', alpha=0.7, label='Model SWE')
            
            # SWE observed overlay if available
            if hasattr(self, 'swe_obs_data') and self.swe_obs_data is not None:
                swe_aligned = self.swe_obs_data.reindex(dates)
                if swe_aligned.notna().sum() > 0:
                    ax_s.plot(dates, swe_aligned.values, color='darkblue', lw=1.2, 
                             ls='--', marker='.', markersize=2, label='Observed SWE')
                    snow_max = max(snow_max, np.nanmax(swe_aligned.values))
            
            ax_s.set_ylabel('SWE (mm)', color='blue')
            ax_s.tick_params(axis='y', labelcolor='blue')
            if snow_max > 0:
                magnitude = 10 ** np.floor(np.log10(max(1, snow_max)))
                nice_interval = max(50, magnitude if snow_max / magnitude > 2 else magnitude / 2)
                max_tick = int(np.ceil(snow_max / nice_interval) * nice_interval)
                ax_s.set_ylim(0, max_tick)
                ax_s.yaxis.set_major_locator(plt.MultipleLocator(nice_interval))
            ax_s.legend(fontsize=7, loc='upper right')
        
        # Panel 3: Soil moisture
        if soil is not None:
            FC = self.param_vars['FC'].get()
            self.axes3v[2].fill_between(dates, 0, soil, color='brown', alpha=0.5)
            self.axes3v[2].axhline(FC, color='brown', ls='--', alpha=0.5, label=f'FC={FC:.0f}')
            self.axes3v[2].set_ylabel('Soil (mm)')
            self.axes3v[2].legend(loc='upper right', fontsize=8)
        
        # Panel 4: Discharge
        if obs is not None:
            self.axes3v[3].plot(dates, obs, color='grey', lw=1.5, label='Observed')
        self.axes3v[3].plot(dates, sim, color='red', lw=1, label='Simulated')
        self.axes3v[3].set_ylabel('Q (m³/s)')
        self.axes3v[3].set_xlabel('Date')
        self.axes3v[3].legend(loc='upper right')
        
        self.fig3v.tight_layout()
        self.canvas3v.draw()
    
    def plot_glacier_results(self):
        if self.glacier_results is None:
            return
        
        dates = self.glacier_results['dates']
        total = self.glacier_results['total_m3s']
        
        for ax in self.axes5.flatten():
            ax.clear()
        
        self.axes5[0,0].plot(dates, self.glacier_results['debris_m3s'], color='saddlebrown', lw=0.5, label='Debris')
        self.axes5[0,0].plot(dates, self.glacier_results['clean_m3s'], color='steelblue', lw=0.5, label='Clean')
        self.axes5[0,0].set_ylabel('Melt (m³/s)')
        self.axes5[0,0].set_title('Daily by Type')
        self.axes5[0,0].legend(fontsize=8)
        
        self.axes5[0,1].fill_between(dates, 0, total, color='coral', alpha=0.6)
        self.axes5[0,1].set_ylabel('Melt (m³/s)')
        self.axes5[0,1].set_title('Total Daily')
        
        df = pd.DataFrame({'date': dates, 'total': total})
        df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
        monthly = df.groupby('month')['total'].mean()
        self.axes5[1,0].plot(monthly.index.to_timestamp(), monthly.values, color='coral', lw=1.5)
        self.axes5[1,0].set_title('Monthly Average')
        
        df['m'] = pd.to_datetime(df['date']).dt.month
        clim = df.groupby('m')['total'].mean()
        self.axes5[1,1].plot(clim.index, clim.values, marker='o', color='coral')
        self.axes5[1,1].set_xlabel('Month')
        self.axes5[1,1].set_title('Climatology')
        
        self.fig5.tight_layout()
        self.canvas5.draw()
    
    def plot_sensitivity(self):
        """Plot sensitivity results for all analyzed parameters (up to 14)."""
        if self.sensitivity_results is None:
            return
        
        # Clear all axes
        for ax in self.axes6.flatten():
            ax.clear()
            ax.axis('off')  # Hide unused subplots initially
        
        # Get list of parameters that were analyzed
        param_names = list(self.sensitivity_results.keys())
        
        for idx, name in enumerate(param_names):
            if idx >= 15:  # Maximum 15 subplots (5x3)
                break
            
            ax = self.axes6.flatten()[idx]
            ax.axis('on')  # Show this subplot
            
            r = self.sensitivity_results[name]
            
            ax.plot(r['range'], r['NSE'], 'b-', lw=2, label='NSE')
            ax.plot(r['range'], r['KGE'], 'g--', lw=2, label='KGE')
            ax.axvline(r['optimal'], color='red', ls=':', lw=2, label='Optimal')
            
            # Mark if it's a NEW parameter
            label = name
            ax.set_xlabel(label, fontweight='bold')
            ax.set_ylabel('Metric')
            ax.legend(fontsize=6, loc='lower right')
            ax.set_ylim(-0.5, 1.0)
            ax.grid(True, alpha=0.3)
        
        self.fig6.suptitle('Parameter Sensitivity Analysis', fontweight='bold')
        self.fig6.tight_layout()
        self.canvas6.draw()
    
    # =========================================================================
    # SAVE/LOAD
    # =========================================================================
    
    def save_model_pkl(self):
        if self.hydro_model is None:
            messagebox.showinfo("Info", "No model to save")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".pkl", filetypes=[("Pickle", "*.pkl")])
        if fp:
            # Attach optimization results to model before saving
            if self.stored_optimized_params:
                self.hydro_model.optimized_params = self.stored_optimized_params.copy()
            if self.best_results:
                self.hydro_model.best_results = self.best_results[:]
            if self.iteration_history:
                self.hydro_model.iteration_history = self.iteration_history[:]
            self.hydro_model.save(fp)
            self.log(f"Saved: {fp} (incl. optimization history & validation metrics)")
    
    def load_saved_model(self):
        fp = filedialog.askopenfilename(filetypes=[("Pickle", "*.pkl")])
        if fp:
            try:
                self.hydro_model = HKPHydroModel.load(fp)
                self.entry_vars['area'].set(str(self.hydro_model.area_km2))
                self.entry_vars['lat'].set(str(self.hydro_model.latitude))
                
                if self.hydro_model.params:
                    for k, v in self.hydro_model.params.items():
                        if k in self.param_vars:
                            self.param_vars[k].set(v)
                            self.param_entries[k].set(f"{v:.4f}")
                
                # Restore optimization history
                if hasattr(self.hydro_model, 'optimized_params') and self.hydro_model.optimized_params:
                    self.stored_optimized_params = self.hydro_model.optimized_params.copy()
                if hasattr(self.hydro_model, 'best_results') and self.hydro_model.best_results:
                    self.best_results = self.hydro_model.best_results[:]
                if hasattr(self.hydro_model, 'iteration_history') and self.hydro_model.iteration_history:
                    self.iteration_history = self.hydro_model.iteration_history[:]
                    self.iteration_count = len(self.iteration_history)
                
                self.elevation_bands = self.hydro_model.elevation_bands
                self.update_elev_bands_display()
                
                extras = []
                if self.stored_optimized_params:
                    extras.append("optimized params")
                if self.iteration_history:
                    extras.append(f"{len(self.iteration_history)} iterations")
                extra_txt = f" + {', '.join(extras)}" if extras else ""
                self.log(f"Loaded: {fp}{extra_txt}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def save_all_results(self):
        if self.results_calib is None:
            messagebox.showinfo("Info", "Run model first")
            return
        
        folder = filedialog.askdirectory()
        if not folder:
            return
        
        try:
            name = self.entry_vars['catchment_name'].get() or "catchment"
            
            df = pd.DataFrame({
                'Date': self.results_calib['dates'],
                'Observed_m3s': self.results_calib.get('obs'),
                'Simulated_m3s': self.results_calib['Q_sim_m3s'],
                'Precipitation_mm': self.results_calib['precip'],
                'Temperature_C': self.results_calib['temp'],
                'Snow_mm': self.results_calib['snow'],
                'Sublimation_mm': self.results_calib.get('sublimation', 0),
                'Soil_mm': self.results_calib['soil']
            })
            df.to_csv(f'{folder}/{name}_calibration.csv', index=False)
            
            if self.results_valid is not None:
                df_v = pd.DataFrame({
                    'Date': self.results_valid['dates'],
                    'Observed_m3s': self.results_valid.get('obs'),
                    'Simulated_m3s': self.results_valid['Q_sim_m3s'],
                    'Precipitation_mm': self.results_valid.get('precip', 0),
                    'Temperature_C': self.results_valid.get('temp', 0),
                    'Snow_mm': self.results_valid.get('snow', 0),
                    'Sublimation_mm': self.results_valid.get('sublimation', 0),
                    'Soil_mm': self.results_valid.get('soil', 0)
                })
                df_v.to_csv(f'{folder}/{name}_validation.csv', index=False)
            
            self.fig1.savefig(f'{folder}/{name}_calibration.png', dpi=300, bbox_inches='tight')
            if self.results_valid is not None:
                self.fig2.savefig(f'{folder}/{name}_validation.png', dpi=300, bbox_inches='tight')
            self.fig3.savefig(f'{folder}/{name}_comprehensive_calib.png', dpi=300, bbox_inches='tight')
            if self.results_valid is not None and hasattr(self, 'fig3v'):
                self.fig3v.savefig(f'{folder}/{name}_comprehensive_valid.png', dpi=300, bbox_inches='tight')
            
            self.log(f"Saved to: {folder}")
            messagebox.showinfo("Success", f"Saved to {folder}")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def quick_save_all(self):
        """Quick Save All: saves model + results + history to a smart default path.
        
        Default path: E:\\Project3\\Catchments\\{catchment_name}\\HKPM
        The base root and sub-folder name are editable in a dialog.
        All folders are created automatically if they don't exist.
        """
        name = self.entry_vars['catchment_name'].get().strip() or "catchment"
        
        # Build dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("⚡ Quick Save All")
        dlg.geometry("540x300")
        dlg.grab_set()
        dlg.resizable(True, False)
        
        ttk.Label(dlg, text="Quick Save All — saves model, history, results & figures",
                  font=('Helvetica', 9, 'bold')).pack(anchor='w', padx=10, pady=(10, 2))
        ttk.Label(dlg, text="Folder will be created automatically if it does not exist.",
                  foreground='gray').pack(anchor='w', padx=10)
        
        # Base root (editable)
        base_frame = ttk.LabelFrame(dlg, text="Base Root Path")
        base_frame.pack(fill=tk.X, padx=10, pady=5)
        base_var = tk.StringVar(value=r"E:\Project3\Catchments")
        base_entry = ttk.Entry(base_frame, textvariable=base_var, width=50)
        base_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        ttk.Button(base_frame, text="Browse",
                   command=lambda: base_var.set(
                       filedialog.askdirectory(title="Select base catchments folder") or base_var.get()
                   )).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Sub-folder name (editable, default HKPM)
        sub_frame = ttk.LabelFrame(dlg, text="Sub-folder name (e.g. HKPM, HKPM1, Results)")
        sub_frame.pack(fill=tk.X, padx=10, pady=5)
        sub_var = tk.StringVar(value="HKPM")
        ttk.Entry(sub_frame, textvariable=sub_var, width=20).pack(anchor='w', padx=5, pady=5)
        
        # Preview
        preview_label = ttk.Label(dlg, text="", foreground='blue')
        preview_label.pack(anchor='w', padx=10, pady=2)
        
        def update_preview(*_):
            b = base_var.get().strip()
            s = sub_var.get().strip() or "HKPM"
            preview_label.config(
                text=f"Save to: {os.path.join(b, name, s)}")
        
        base_var.trace_add('write', update_preview)
        sub_var.trace_add('write', update_preview)
        update_preview()
        
        result = {'ok': False}
        
        def do_save():
            base = base_var.get().strip()
            sub = sub_var.get().strip() or "HKPM"
            folder = os.path.join(base, name, sub)
            
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create folder:\n{folder}\n\n{e}", parent=dlg)
                return
            
            saved = []
            errors = []
            
            # 1. Save model (.pkl)
            try:
                pkl_path = os.path.join(folder, f"{name}.pkl")
                if self.hydro_model is not None:
                    if self.stored_optimized_params:
                        self.hydro_model.optimized_params = self.stored_optimized_params.copy()
                    if self.best_results:
                        self.hydro_model.best_results = self.best_results[:]
                    if self.iteration_history:
                        self.hydro_model.iteration_history = self.iteration_history[:]
                    self.hydro_model.save(pkl_path)
                    saved.append(f"Model: {name}.pkl")
            except Exception as e:
                errors.append(f"Model: {e}")
            
            # 2. Save optimization history (.csv)
            try:
                if self.iteration_history:
                    rows = []
                    for h in self.iteration_history:
                        row = {'iteration': h['iteration'], 'obj': h['obj'],
                               'cal_NSE': h['NSE'], 'cal_NSE_log': h['NSE_log'],
                               'cal_KGE': h['KGE'], 'cal_PBIAS': h['PBIAS'],
                               'val_NSE': h.get('val_NSE', ''),
                               'val_KGE': h.get('val_KGE', ''),
                               'val_PBIAS': h.get('val_PBIAS', '')}
                        for k in ['val_NSE', 'val_KGE', 'val_PBIAS']:
                            if isinstance(row[k], float) and np.isnan(row[k]):
                                row[k] = ''
                        row.update(h['params'])
                        rows.append(row)
                    hist_path = os.path.join(folder, f"{name}.csv")
                    pd.DataFrame(rows).to_csv(hist_path, index=False)
                    saved.append(f"Opt. history: {name}.csv")
            except Exception as e:
                errors.append(f"History: {e}")
            
            # 3. Save calibration results
            try:
                if self.results_calib is not None:
                    df = pd.DataFrame({
                        'Date': self.results_calib['dates'],
                        'Observed_m3s': self.results_calib.get('obs'),
                        'Simulated_m3s': self.results_calib['Q_sim_m3s'],
                        'Precipitation_mm': self.results_calib['precip'],
                        'Temperature_C': self.results_calib['temp'],
                        'Snow_mm': self.results_calib['snow'],
                        'Sublimation_mm': self.results_calib.get('sublimation', 0),
                        'Soil_mm': self.results_calib['soil']
                    })
                    df.to_csv(os.path.join(folder, f"{name}_calibration.csv"), index=False)
                    saved.append(f"Calibration: {name}_calibration.csv")
            except Exception as e:
                errors.append(f"Calibration CSV: {e}")
            
            # 4. Save validation results
            try:
                if self.results_valid is not None:
                    df_v = pd.DataFrame({
                        'Date': self.results_valid['dates'],
                        'Observed_m3s': self.results_valid.get('obs'),
                        'Simulated_m3s': self.results_valid['Q_sim_m3s'],
                        'Precipitation_mm': self.results_valid.get('precip', 0),
                        'Temperature_C': self.results_valid.get('temp', 0),
                        'Snow_mm': self.results_valid.get('snow', 0),
                        'Sublimation_mm': self.results_valid.get('sublimation', 0),
                        'Soil_mm': self.results_valid.get('soil', 0)
                    })
                    df_v.to_csv(os.path.join(folder, f"{name}_validation.csv"), index=False)
                    saved.append(f"Validation: {name}_validation.csv")
            except Exception as e:
                errors.append(f"Validation CSV: {e}")
            
            # 5. Save figures
            try:
                if self.results_calib is not None:
                    self.fig1.savefig(os.path.join(folder, f"{name}_calibration.png"), dpi=300, bbox_inches='tight')
                    self.fig3.savefig(os.path.join(folder, f"{name}_comprehensive_calib.png"), dpi=300, bbox_inches='tight')
                    saved.append("Calibration figures (.png)")
            except Exception as e:
                errors.append(f"Calib figure: {e}")
            
            try:
                if self.results_valid is not None:
                    self.fig2.savefig(os.path.join(folder, f"{name}_validation.png"), dpi=300, bbox_inches='tight')
                    if hasattr(self, 'fig3v'):
                        self.fig3v.savefig(os.path.join(folder, f"{name}_comprehensive_valid.png"), dpi=300, bbox_inches='tight')
                    saved.append("Validation figures (.png)")
            except Exception as e:
                errors.append(f"Valid figure: {e}")
            
            # Report
            msg = f"Quick Save Complete!\nFolder: {folder}\n\nSaved:\n"
            msg += "\n".join(f"  ✓ {s}" for s in saved)
            if errors:
                msg += "\n\nWarnings:\n"
                msg += "\n".join(f"  ✗ {e}" for e in errors)
            
            self.log(f"Quick Save → {folder} ({len(saved)} items saved)")
            messagebox.showinfo("Quick Save Complete", msg, parent=dlg)
            result['ok'] = True
            dlg.destroy()
        
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="💾 Save Now", command=do_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=5)
        
        dlg.wait_window()
    
    # =========================================================================
    # HELP
    # =========================================================================
    
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
    
    def show_about(self):
        text = f"""
{APP_NAME}
Version: {APP_VERSION}

Author: {AUTHOR}
{AFFILIATION}

GitHub: {GITHUB_URL}

14 Parameters (with optional sublimation):
  Tt, Cm, Csub, FC, beta, alpha, Kq, Ki, Ks,
  lapse_rate, Imax, GWexch, ETmult, LP

Features:
- Catchment type presets: Alpine, Lowland, Universal
- Active module toggles (Snow, Sublimation, Interception, Interflow, GW Exchange)
- Auto-load data from folder structure
- Default / Extended / Very Extended optimization bounds
- Apply Optimized → Fixed for multi-round optimization
- Use Optimized button (preserves values after manual changes)
- 6 optimization algorithms (DE, PSO, SCE-UA, Adaptive DE, Basin Hopping, L-BFGS-B)
- Elevation bands (semi-distributed)
- Glacier melt: External CSV or Integrated model
- Flow data: Separate calib/valid files or single file auto-split
- Export iteration history to Excel
- Comprehensive hydrograph and component plots
- Validation with independent period
- Ungauged catchment prediction
"""
        messagebox.showinfo("About", text)
    
    def show_user_guide(self):
        guide = f"""
{APP_SHORT_NAME} v{APP_VERSION} - USER GUIDE
{'='*55}

CATCHMENT SETUP
===============
1. Select Catchment Type: Alpine / Lowland / Universal
   - Alpine: Snow ✓, Sublimation ✓, Interception ✗, GW Exchange ✗
   - Lowland: Snow ✗, Interception ✓, GW Exchange ✓
   - Universal: All modules active (recommended default)

2. Active Modules: Override automatic presets if needed
   - Snow module: Cold regions with snowfall
   - Sublimation: Cold arid high-mountain snow loss
   - Interception: Forests, vegetation canopy storage
   - Interflow: 3-pathway routing (quick + interflow + baseflow)
   - GW Exchange: Gaining/losing stream interaction

3. Enter catchment info (name, area, lat/lon) or load from shapefile

AUTO-LOAD FROM FOLDER
=====================
Set Base Path (default: E:\\Project3\\Catchments) and enter catchment
folder name, then click Auto-Load. Expected structure:
  {{name}}/shapefile/{{name}}_UTM.shp          → area, lat, lon
  {{name}}/PPT/CHIRPS_{{name}}_*.nc            → precipitation
  {{name}}/Temperature/GLDAS_Temp_{{name}}_*.nc → temperature
  {{name}}/Streamflow_data/calib.csv           → calibration flow
  {{name}}/Streamflow_data/valid.csv           → validation flow
  {{name}}/Glacier_polygon/Glacier_Melt/...csv → glacier (optional)
  {{name}}/Catchment_Characteristics/..._Elevation_Bands.xlsx (optional)

PARAMETERS (14) — Literature-Based Bounds
===============
Snow & Temperature:
  Tt     Temperature threshold (°C)         Default: -3 to 3
  Cm     Melt coefficient (mm/°C/day)       Default: 0.5 to 12
  Csub   Sublimation coeff. (fraction)      Default: 0 to 1.0
         (Stigter et al. 2021; HKH sublimation 15-45% snowfall)

Soil Moisture:
  FC     Field capacity (mm)                Default: 10 to 600
  beta   Runoff shape parameter (-)         Default: 0.5 to 6.0
  LP     ET threshold (fraction of FC)      Default: 0.1 to 1.0

Routing:
  alpha  Quick flow fraction (-)            Default: 0.01 to 0.99
  Kq     Quick flow recession (1/day)       Default: 0.01 to 0.999
  Ki     Interflow recession (1/day)        Default: 0.0001 to 0.8
  Ks     Slow flow recession (1/day)        Default: 0.0001 to 0.1

Corrections & Exchange:
  lapse_rate  Temp lapse rate (°C/km)       Default: 4 to 10
  ETmult      PET correction factor (-)     Default: 0.3 to 2.0
  Imax        Interception capacity (mm)    Default: 0 to 6
  GWexch      GW exchange (mm/d)            Default: -3 to 3
              (+gaining / -losing streams)

Key References:
  Hock (2003) J.Hydrol; Seibert & Vis (2012) HESS;
  Lutz et al. (2016) Nat.Clim.Change; Stigter et al. (2021) Cryosphere;
  Immerzeel et al. (2010, 2014) Nature/NCC

OPTIMIZATION
============
1. Check parameters to optimize (✓)
2. Uncheck to fix at specific value in Fixed column
3. Set Min/Max bounds (or use Reset Default / Reset Extended)
4. Choose algorithm: DE (recommended), PSO, SCE-UA, etc.
5. Enable Auto-stop to save time

After optimization:
- "Use Optimized" restores the optimization result (even after
  manual parameter changes - values are permanently stored)
- "Apply Optimized → Fixed" copies optimized values to Fixed column
  for multi-round optimization (fix some, optimize remaining)

MULTI-ROUND OPTIMIZATION
=========================
1. Run optimization with all parameters checked
2. Click "Apply Optimized → Fixed"
3. Uncheck well-calibrated parameters (e.g., FC, Ks)
4. Check sensitive parameters for further tuning
5. Run optimization again with narrower bounds

GLACIER OPTIONS
===============
- None: No glacier input
- External: Load pre-calculated glacier melt CSV
- Integrated: Use internal glacier model with shapefile

OPTIMIZATION — CALIBRATION ONLY (FASTER)
=========================================
Optimization runs ONLY on the calibration period for maximum speed.
Validation is computed ONCE after optimization finishes — not every iteration.
This significantly reduces computation time for long validation periods.

After optimization completes:
- Full validation metrics are shown in the results summary
- Click "Run Validation" in the Calibration tab to see the hydrograph
- Or click "Apply Optimized → Fixed" for multi-round optimization

QUICK SAVE ALL (⚡ File → Quick Save All)
==========================================
Saves everything in one click to a smart default path:
  E:\\Project3\\Catchments\\{{catchment_name}}\\HKPM

You can edit:
  - Base root: E:\\Project3\\Catchments\\
  - Sub-folder: HKPM (or HKPM1, Results, etc.)

Automatically creates the folder if it doesn't exist. Saves:
  {{name}}.pkl             → Model (with optimization history)
  {{name}}.csv             → Full optimization iteration history
  {{name}}_calibration.csv → Calibration timeseries
  {{name}}_validation.csv  → Validation timeseries (if available)
  {{name}}_calibration.png → Calibration hydrograph
  {{name}}_validation.png  → Validation hydrograph
  {{name}}_comprehensive_calib.png / _valid.png

The original File → Save Model, Save All Results options remain unchanged.
===============
Load from CSV/Excel file with columns:
  elevation (m) | area_fraction (0-1)
Enables semi-distributed temperature adjustment using lapse rate.
Recommended for mountain catchments with >500m elevation range.

EXPORT
======
- Export iteration history to Excel (all iterations + parameters)
- Export figures via matplotlib toolbar
"""
        win = tk.Toplevel(self.root)
        win.title("User Guide")
        win.geometry("600x750")
        text = ScrolledText(win, font=('Consolas', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert('1.0', guide)
        text.config(state=tk.DISABLED)


# =============================================================================
# MAIN
# =============================================================================

def main():
    root = tk.Tk()
    app = HKPHM_GUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
