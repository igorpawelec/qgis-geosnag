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
3. The first run installs numba, scipy, scikit-learn, joblib, rasterio, fiona and shapely with `pip --target` into the plugin's own `libs/` folder (the log shows the exact command if that fails on a locked-down machine) and downloads the models of the chosen band mode (60–145 MB) into the user's cache, `~/.cache/pygeosnag/assets-v2`. A local models folder can be given instead, under *Advanced*; it is remembered.

Why `libs/` and not `pip --user`: the user site-packages folder is read by every Python of the same minor version on the machine, conda environments included, so a plugin that installs there can silently replace packages in environments that have nothing to do with QGIS. This plugin's dependencies stay inside the plugin.

## Use

Processing toolbox → GeoSnag → *Detect dead trees*. Band mode *auto* reads 4 bands as R, G, B, NIR (NIR, R, G, B when the first band is the brightest) and 3 bands as CIR when the second band is the darkest over a sample of the pixels, else as RGB; the first log line says which, and the explicit modes override it. The threshold defaults to the models' operating point, 0.7: on a scene never seen in training recall stays flat from 0.6 to 0.8 while precision rises, so lower it for completeness and raise it for a cleaner map. On imagery unlike the training sites (Polish lowland pine and spruce, 0.25 m, leaf-on; another camera, species or decay stage) the ranking is usually right and the scale is not, so lower it until the obvious snags appear. Add stand polygons with a stand age field if you have them: on seven test sites they removed a quarter of the points and, in a field review, only roads and fields.

Then *Grow crowns* with the orthophoto and the points.

What to expect (models `assets-v2`: whole-crown labels, ten Polish sites, the site under test never seen in training, a hit within 1.5 m of a reference top): F1 0.61 for RGB+NIR, 0.55 for CIR and for RGB. On Białowieża, a 2018 flight never trained on, 61% of the trees dead by the flight at the operating point, with a precision floor of 26% against an ALS reference that is not the image's. The RGB+NIR and CIR models score spectral means standardised within the scene (a first pass over 16 tiles), which is what carries them to a flight with a different colour balance; the option sits under *Advanced* and should stay on auto. RGB+NIR points also carry `p_object`, a second, stricter score; a cut at 0.4 (*Advanced*) keeps about two thirds of the trees at half the false points. Since 0.4.4 a hazy or flat scene is mapped per band onto the training radiometric range before segmentation (*Radiometry* under *Advanced*, default auto): measured on 200 Polish AOIs, 48 scenes needed it, and on some of them the models saw nothing at all without it.

## Testing without QGIS

`test_package_calls.py` runs the package calls the algorithms make, on the test raster and dead-tree points shipped with pygeoadaptels, from any Python that has the packages (set `PYGEOSNAG_ASSETS` to a folder with the models). The parameter glue and the in-QGIS runtime are tested in a live QGIS.

## License

GPL-3.0-or-later. Copyright Igor Pawelec.
