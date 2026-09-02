# GeoSnag — QGIS plugin

<img src="https://raw.githubusercontent.com/igorpawelec/qgis-geosnag/main/geosnag_plugin/icon.png" align="right" width="96"/>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**Standing dead tree (snag) detection on aerial orthophotos, in the Processing toolbox.**

A Processing provider for the [pygeosnag](https://github.com/igorpawelec/pygeosnag) package. The algorithms live in the package; this plugin is glue. Two algorithms:

- **Detect dead trees** — orthophoto in, GeoPackage of dead-crown polygons with a confidence score out. Band mode (RGB+NIR, CIR, RGB), probability threshold, optional stand mask from forest-management polygons, optional object forest, optional centroid layer and probability raster.
- **Adapt model** — teach the detector a scene it gets wrong from a few labelled points (dead trees, and optionally rejected objects), producing a model file for *Detect dead trees*.

## Install

1. Download the zip from the releases page (or build it with `python build_zip.py`, which copies pygeosnag, pygeoadaptels and pygeopalette from the sibling checkouts into `vendor/`).
2. QGIS → Plugins → Manage and Install Plugins → Install from ZIP.
3. The first run installs numba, scipy, scikit-learn, joblib, rasterio, fiona and shapely into QGIS's own Python (the log shows the exact command if that fails on a locked-down machine) and downloads the models of the chosen band mode (40–60 MB) into the user's cache. A local models folder can be given instead, under *Advanced*.

## Use

Processing toolbox → GeoSnag → *Detect dead trees*. Five things on the dialog: the orthophoto, the band mode (*auto* for R, G, B, NIR or R, G, B in that order; *cir* for NIR, R, G), the threshold (keep 0.5 unless you know why), optional stand polygons with a stand age field (on seven test sites they removed a quarter of the objects and, in a field review, only roads and fields), and the output. Everything else is under *Advanced* with the calibrated defaults, including the local models folder: give it once and it is remembered.

If the result is poor on a new kind of scene (different camera, species or decay stage), mark a few dead trees as points, optionally a few objects you reject, and run *Adapt model*; give its output to *Detect dead trees* as the adapted model.

What to expect, measured with the site under test never seen in training: recall about 65%, precision 31% against an incomplete reference and roughly 55–75% after a field review; RGB and CIR about 15% below RGB+NIR. Details, evidence and every constant are in the pygeosnag README and the research report behind it.

## Testing without QGIS

`test_package_calls.py` runs the package calls the algorithms make, on the test raster shipped with pygeoadaptels, from any Python that has the packages (set `PYGEOSNAG_ASSETS` to a folder with the models). The parameter glue and the in-QGIS runtime are tested in a live QGIS.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
