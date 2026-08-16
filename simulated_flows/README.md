# Simulated daily discharge — 35 Afghan catchments

This folder contains the **simulated** daily discharge series produced by the
calibrated HKPM-HM v1.0 model for the 35 study catchments of the accompanying
paper, covering each catchment's calibration and validation periods.

**Why simulated flows only?** The observed streamflow records used for
calibration and validation were provided by the Afghanistan Ministry of Energy
and Water (MEW) and are subject to MEW's data-sharing policy; they can
therefore not be redistributed here. The simulated series are published so
that every hydrograph, metric, and figure of the paper can be inspected and
reused. Observed data may be requested from MEW directly.

## File format

One CSV file per catchment, named `<Catchment>_simulated_flow.csv`
(spaces in catchment names replaced by underscores, e.g. `Shash_Pul_...`):

| Column | Description |
|---|---|
| `Date` | Calendar date (YYYY-MM-DD), daily time step |
| `Simulated_m3s` | Simulated discharge at the catchment outlet (m³ s⁻¹) |
| `Period` | `calibration` or `validation` (periods as used in the paper) |

For some catchments a gap separates the calibration and validation periods;
the periods are exactly those used in the paper (they follow the availability
and quality of the observed records). The first weeks of each run were used
for model spin-up and are not part of the series.

## Glacier representation

Each series comes from the model configuration that represents the actual
cryospheric status of the catchment:

- **29 glacierized catchments** were simulated **with the glacier module
  active**, forced by the multi-temporal Landsat glacier inventory
  ([HKPM-Glacier-Inventory-GEE](https://github.com/mnajimnasimi/HKPM-Glacier-Inventory-GEE)).
- **6 catchments without (significant) glacier cover** were simulated
  **without the glacier module**: Cheghcheran, Dawlatyar, Pul-i-Ashawa, Tang-i-Sayedan, Tirin, Waras.
  (Pul-i-Ashawa and Tang-i-Sayedan hold only negligible glacier area,
  < 0.2 % of the catchment, and are therefore modelled glacier-free.)

The with/without-glacier sensitivity comparison for the glacierized
catchments is presented in the paper and in its supplementary catchment
atlas (ESM 3); the series published here are the primary (glacier-aware)
simulations.

## Catchment overview

Parameter estimation combined automatic optimization with manual refinement
where required; the calibrated parameter values for all 35 catchments are
tabulated in the paper (ESM 4). Performance metrics below were computed from
the published series and match the paper's per-catchment atlas (ESM 3).

| # | Catchment | Area (km²) | Glacier module | Configuration | Calibration period | Validation period | NSE (cal.) | NSE (val.) | KGE (val.) |
|---:|---|---:|:---:|---|---|---|---:|---:|---:|
| 1 | Anjuman | 1,597.1 | on | SM_IF_IC | 2010-01-31 – 2011-12-31 | 2013-01-31 – 2013-12-31 | 0.777 | 0.828 | 0.763 |
| 2 | Asmar | 19,783.9 | on | SM_IF_GW_SUB | 2017-01-01 – 2018-12-31 | 2019-01-01 – 2020-09-30 | 0.792 | 0.813 | 0.780 |
| 3 | Bagh-i-Omomi | 201.3 | on | SM_IF_GW_SUB_IC | 2009-01-31 – 2016-12-31 | 2017-01-31 – 2020-09-30 | 0.692 | 0.670 | 0.763 |
| 4 | Balay-i-Kelagai | 16,914.0 | on | SM_IF_GW_SUB | 2009-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.641 | 0.766 | 0.821 |
| 5 | Chaghasarai | 3,848.3 | on | SM_IF_GW | 2011-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.714 | 0.835 | 0.798 |
| 6 | Cheghcheran | 6,117.1 | off | SM_IF_SUB_IC | 2009-01-01 – 2016-12-31 | 2017-01-01 – 2021-09-30 | 0.787 | 0.861 | 0.930 |
| 7 | Dakah | 67,600.2 | on | SM_IF_SUB | 2008-01-01 – 2015-12-31 | 2018-01-01 – 2020-09-30 | 0.763 | 0.760 | 0.759 |
| 8 | Dawlatyar | 2,900.5 | off | SM_IF_IC | 2010-01-01 – 2017-12-31 | 2018-01-01 – 2020-09-30 | 0.640 | 0.732 | 0.720 |
| 9 | Doabi | 702.7 | on | SM_IF_GW_IC | 2011-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.631 | 0.761 | 0.852 |
| 10 | Doshi | 3,730.4 | on | SM_IF_GW_SUB | 2009-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.718 | 0.705 | 0.812 |
| 11 | Eshkashem | 13,770.8 | on | SM_IF_GW | 2012-01-01 – 2014-12-31 | 2017-01-01 – 2020-09-30 | 0.772 | 0.915 | 0.875 |
| 12 | Faizabad | 13,190.8 | on | SM_IF_GW_IC | 2012-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.870 | 0.826 | 0.907 |
| 13 | Gardandiwal | 861.9 | on | SM_IF_IC | 2015-01-01 – 2016-12-31 | 2018-01-01 – 2020-12-31 | 0.836 | 0.759 | 0.734 |
| 14 | Keraman | 546.8 | on | SM_IF_GW_SUB | 2013-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.727 | 0.714 | 0.716 |
| 15 | Keshem | 2,176.2 | on | SM_IF_GW_SUB | 2015-01-01 – 2017-12-31 | 2018-01-01 – 2020-09-30 | 0.656 | 0.726 | 0.773 |
| 16 | Khawak | 1,351.8 | on | SM_IF_GW_SUB | 2011-01-01 – 2016-12-31 | 2018-01-01 – 2020-09-30 | 0.645 | 0.751 | 0.809 |
| 17 | Khwajaghar | 20,771.8 | on | SM_IF_GW_SUB | 2012-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.760 | 0.821 | 0.911 |
| 18 | Kofab | 1,080.0 | on | SM_IF | 2010-01-20 – 2013-12-31 | 2014-01-01 – 2020-09-30 | 0.823 | 0.906 | 0.857 |
| 19 | Nawabad | 23,813.3 | on | SM_IF_GW_SUB | 2012-01-01 – 2014-12-31 | 2015-01-01 – 2018-12-31 | 0.657 | 0.720 | 0.607 |
| 20 | Nazdik-i-Jurm | 7,737.2 | on | SM_IF_SUB | 2009-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.815 | 0.835 | 0.902 |
| 21 | Nazdik-i-Keshem | 16,875.2 | on | SM_IF | 2014-01-31 – 2017-12-31 | 2018-01-31 – 2020-09-30 | 0.801 | 0.803 | 0.846 |
| 22 | Omarz | 2,223.9 | on | SM_IF_GW_IC | 2012-01-01 – 2014-12-31 | 2015-01-01 – 2018-12-30 | 0.861 | 0.849 | 0.812 |
| 23 | Pul-i-Ashawa | 4,038.4 | off | SM_IF_GW | 2013-01-31 – 2015-12-31 | 2016-01-31 – 2017-12-31 | 0.880 | 0.847 | 0.907 |
| 24 | Pul-i-Baraq | 14,072.8 | on | SM_IF_GW | 2013-01-31 – 2015-12-31 | 2016-01-31 – 2019-09-30 | 0.623 | 0.781 | 0.881 |
| 25 | Pul-i-Kundasang | 12,623.1 | on | SM_IF_SUB_IC | 2013-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.784 | 0.720 | 0.855 |
| 26 | Pul-i-Nalyar | 3,989.2 | on | SM_IF_GW_IC | 2011-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.609 | 0.706 | 0.574 |
| 27 | Pul-i-Qarghayi | 6,204.2 | on | SM_IF_GW | 2007-04-20 – 2016-12-31 | 2017-01-31 – 2020-09-30 | 0.686 | 0.675 | 0.618 |
| 28 | Shash Pul | 4,441.5 | on | SM_IF_SUB_IC | 2011-01-01 – 2016-12-31 | 2017-01-01 – 2020-09-30 | 0.826 | 0.805 | 0.876 |
| 29 | Sheghnan | 30,227.9 | on | SM_IF_GW | 2013-01-01 – 2014-12-31 | 2016-10-01 – 2019-12-31 | 0.753 | 0.733 | 0.782 |
| 30 | Shokhi | 10,878.4 | on | SM_IF_SUB_IC | 2007-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.631 | 0.686 | 0.799 |
| 31 | Sust | 4,556.6 | on | SM_IF_IC | 2015-01-01 – 2017-12-31 | 2018-01-01 – 2020-09-30 | 0.736 | 0.807 | 0.878 |
| 32 | Tang-i-Gulbahar | 3,539.6 | on | SM_IF_GW_SUB_IC | 2009-01-01 – 2015-12-31 | 2016-01-01 – 2020-09-30 | 0.732 | 0.769 | 0.875 |
| 33 | Tang-i-Sayedan | 1,644.3 | off | SM_IF | 2012-01-01 – 2014-12-31 | 2016-01-01 – 2020-09-30 | 0.504 | 0.700 | 0.580 |
| 34 | Tirin | 5,505.5 | off | SM_IF_SUB_IC | 2019-01-01 – 2019-12-31 | 2020-01-01 – 2020-09-30 | 0.564 | 0.695 | 0.836 |
| 35 | Waras | 1,699.3 | off | SM_IF_GW_IC | 2013-01-31 – 2015-12-31 | 2017-01-31 – 2017-12-30 | 0.688 | 0.894 | 0.866 |

## Citation

If you use these series, please cite the accompanying paper (reference will
be added upon publication) and the model repository:

> Nasimi, M. N. (2026). *HKPM-HM — Hindu Kush Pamir Mountains Hydrological
> Model* (Version 1.0.0) [Computer software].
> https://github.com/mnajimnasimi/HKPM-HM
