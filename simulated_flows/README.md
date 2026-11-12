# Simulated daily discharge — 35 Afghan catchments

This folder contains the **simulated** daily discharge series produced by the
calibrated HKPM-HM v1.0 model for the 35 study catchments of the accompanying
paper, covering each catchment's calibration and validation periods.

**Why simulated flows only?** The observed streamflow records used for
calibration and validation were provided by the Afghanistan Ministry of Energy
and Water (MEW) and are subject to MEW's data-sharing policy; they can
therefore not be redistributed here. The simulated series are published so
that the hydrographs of the paper can be inspected and reused. Observed data
may be requested from MEW directly.

## File format

One CSV file per catchment, named `<Catchment>_simulated_flow.csv`
(spaces in catchment names replaced by underscores, e.g. `Shash_Pul_...`):

| Column | Description |
|---|---|
| `Date` | Calendar date (YYYY-MM-DD), daily time step |
| `Simulated_m3s` | Simulated discharge at the catchment outlet (m³ s⁻¹) |
| `Period` | `calibration` or `validation` (periods as used in the paper) |

For some catchments a gap separates the calibration and validation periods;
the periods are those used in the paper (they follow the availability and
quality of the observed records). Every run starts with a spin-up of two
years. The first 30 days of each period are the warm-up of the evaluation and
are not part of the series, so a series begins 30 days after the start of its
period.

## How the series were produced

All 35 catchments were calibrated with the same automatic procedure, on the
calibration period only and without manual adjustment. The settings are
listed in the appendix of the manual
([`docs/HKPM_HM_Technical_Manual_and_User_Guide.pdf`](../docs/HKPM_HM_Technical_Manual_and_User_Guide.pdf));
the paper describes the procedure and the tests of its results.

The glacier module is active in all catchments. It adds ice melt wherever the
glacier inventory
([HKPM-Glacier-Inventory-GEE](https://github.com/mnajimnasimi/HKPM-Glacier-Inventory-GEE))
has ice in the catchment, from the ice area per 100 m elevation band and ice
type with fixed degree-day factors, and it has no calibrated parameter.

The quality of the simulations differs between the catchments. The
performance measures of every catchment, the parameter values and the
hydrographs with the observed discharge are given in the paper and its
supplementary material. Please consult them before a series is used for an
application.

## Catchment overview

Periods as in the paper (year-month).

| # | Catchment | Area (km²) | Calibration period | Validation period |
|---:|---|---:|---|---|
| 1 | Anjuman | 1,597 | 2010-01 to 2011-12 | 2013-01 to 2013-12 |
| 2 | Asmar | 19,784 | 2017-01 to 2018-12 | 2019-01 to 2020-09 |
| 3 | Bagh-i-Omomi | 201 | 2009-01 to 2016-12 | 2017-01 to 2020-09 |
| 4 | Balay-i-Kelagai | 16,914 | 2009-01 to 2016-12 | 2017-01 to 2020-09 |
| 5 | Chaghasarai | 3,848 | 2011-01 to 2016-12 | 2017-01 to 2020-09 |
| 6 | Cheghcheran | 6,117 | 2009-01 to 2016-12 | 2017-01 to 2021-09 |
| 7 | Dakah | 67,600 | 2008-01 to 2015-12 | 2018-01 to 2020-09 |
| 8 | Dawlatyar | 2,901 | 2010-01 to 2017-12 | 2018-01 to 2020-09 |
| 9 | Doabi | 703 | 2011-01 to 2016-12 | 2017-01 to 2020-09 |
| 10 | Doshi | 3,730 | 2009-01 to 2016-12 | 2017-01 to 2020-09 |
| 11 | Eshkashem | 13,771 | 2012-01 to 2014-12 | 2017-01 to 2020-09 |
| 12 | Faizabad | 13,191 | 2012-01 to 2015-12 | 2016-01 to 2020-09 |
| 13 | Gardandiwal | 862 | 2015-01 to 2016-12 | 2018-01 to 2020-12 |
| 14 | Keraman | 547 | 2013-01 to 2015-12 | 2016-01 to 2020-09 |
| 15 | Keshem | 2,176 | 2015-01 to 2017-12 | 2018-01 to 2020-09 |
| 16 | Khawak | 1,352 | 2011-01 to 2016-12 | 2018-01 to 2020-09 |
| 17 | Khwajaghar | 20,772 | 2012-01 to 2015-12 | 2016-01 to 2020-09 |
| 18 | Kofab | 1,080 | 2010-01 to 2013-12 | 2014-01 to 2020-09 |
| 19 | Nawabad | 23,813 | 2012-01 to 2014-12 | 2015-01 to 2018-12 |
| 20 | Nazdik-i-Jurm | 7,737 | 2009-01 to 2015-12 | 2016-01 to 2020-09 |
| 21 | Nazdik-i-Keshem | 16,875 | 2014-01 to 2017-12 | 2018-01 to 2020-09 |
| 22 | Omarz | 2,224 | 2012-01 to 2014-12 | 2015-01 to 2018-12 |
| 23 | Pul-i-Ashawa | 4,038 | 2013-02 to 2015-12 | 2016-01 to 2017-12 |
| 24 | Pul-i-Baraq | 14,073 | 2013-01 to 2015-12 | 2016-01 to 2019-09 |
| 25 | Pul-i-Kundasang | 12,623 | 2013-01 to 2015-12 | 2016-01 to 2020-09 |
| 26 | Pul-i-Nalyar | 3,989 | 2011-01 to 2016-12 | 2017-01 to 2020-09 |
| 27 | Pul-i-Qarghayi | 6,204 | 2007-04 to 2016-12 | 2017-01 to 2020-09 |
| 28 | Shash Pul | 4,442 | 2011-01 to 2016-12 | 2017-01 to 2020-09 |
| 29 | Sheghnan | 30,228 | 2013-01 to 2014-12 | 2016-10 to 2019-12 |
| 30 | Shokhi | 10,878 | 2007-01 to 2015-12 | 2016-01 to 2020-09 |
| 31 | Sust | 4,557 | 2015-01 to 2017-12 | 2018-01 to 2020-09 |
| 32 | Tang-i-Gulbahar | 3,540 | 2009-01 to 2015-12 | 2016-01 to 2020-09 |
| 33 | Tang-i-Sayedan | 1,644 | 2012-01 to 2014-12 | 2016-01 to 2020-09 |
| 34 | Tirin | 5,505 | 2019-01 to 2019-12 | 2020-01 to 2020-09 |
| 35 | Waras | 1,699 | 2013-01 to 2015-12 | 2017-01 to 2017-12 |

## Citation

If you use these series, please cite the accompanying paper (reference will
be added upon publication) and the model repository:

> Nasimi, M. N. (2026). *HKPM-HM — Hindu Kush Pamir Mountains Hydrological
> Model* (Version 1.0.1) [Computer software].
> https://github.com/mnajimnasimi/HKPM-HM, https://doi.org/10.5281/zenodo.21966639
