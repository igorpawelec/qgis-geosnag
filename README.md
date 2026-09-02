# GeoSnag — QGIS plugin

<img src="https://raw.githubusercontent.com/igorpawelec/qgis-geosnag/main/geosnag_plugin/icon.png" align="right" width="96"/>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**Standing dead trees on aerial orthophotos: one point per tree, then the crowns grown from the points.**

A Processing provider for the [pygeosnag](https://github.com/igorpawelec/pygeosnag) package. The algorithms live in the package; this plugin is glue. Two algorithms:

- **Detect dead trees** — orthophoto in (RGB+NIR, CIR or RGB), one point per standing dead tree out, with a confidence `p`. Five things on the dialog: the orthophoto, the band mode, the threshold, optional stand polygons, the output.
- **Grow crowns** — the points plus the orthophoto in, crown polygons out: pygeoadaptels' seeded region growing (inverse OBIA) on CIELAB with a crown recipe. The points can also come from a click or a field survey.

## Install

1. Download the zip from the releases page (or build it with `python build_zip.py`, which copies pygeosnag, pygeoadaptels and pygeopalette from the sibling checkouts into `vendor/`).
2. QGIS → Plugins → Manage and Install Plugins → Install from ZIP.
3. The first run installs numba, scipy, scikit-learn, joblib, rasterio, fiona and shapely with `pip --target` into the plugin's own `libs/` folder (the log shows the exact command if that fails on a locked-down machine) and downloads the models of the chosen band mode (40–60 MB) into the user's cache, `~/.cache/pygeosnag/assets-v1`. A local models folder can be given instead, under *Advanced*; it is remembered.

Why `libs/` and not `pip --user`: the user site-packages folder is read by every Python of the same minor version on the machine, conda environments included, so a plugin that installs there can silently replace packages in environments that have nothing to do with QGIS. This plugin's dependencies stay inside the plugin.

## Use

Processing toolbox → GeoSnag → *Detect dead trees*. Leave the band mode on *auto* for R, G, B, NIR or R, G, B in that order; choose *cir* for NIR, R, G. Keep the threshold at 0.5 on imagery like the training sites (Polish lowland pine and spruce, 0.25 m, leaf-on); on an unfamiliar scene the ranking is usually right and the scale is not, so lower it until the obvious snags appear. Add stand polygons with a stand age field if you have them: on seven test sites they removed a quarter of the points and, in a field review, only roads and fields.

Then *Grow crowns* with the orthophoto and the points.

What to expect, measured with the site under test never seen in training and a hit counted within 1.5 m of a reference top: recall 63%, precision 33% against an incomplete reference and 55–75% after a field review; points a median 0.47 m from the top. RGB and CIR run about 15% below RGB+NIR.

## Testing without QGIS

`test_package_calls.py` runs the package calls the algorithms make, on the test raster and dead-tree points shipped with pygeoadaptels, from any Python that has the packages (set `PYGEOSNAG_ASSETS` to a folder with the models). The parameter glue and the in-QGIS runtime are tested in a live QGIS.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
