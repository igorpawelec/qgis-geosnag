"""Exercise the package calls the algorithms make, WITHOUT QGIS.

This is what can be verified here; the parameter glue and the in-QGIS
runtime are tested in a live QGIS. Runs pygeosnag.detect and
pygeosnag.adapt on the SNP_21_2020_1 test raster shipped with pygeoadaptels
and its dead-tree points, in the rgb mode, with the progress callback the
plugin uses.

    set PYGEOSNAG_ASSETS=<folder with the models and manifest.json>
    D:/miniforge3/envs/ml/python.exe test_package_calls.py
"""
import os
import sys
import tempfile

DATA = "D:/Apps/pygeoadaptels/test_data"
RGB = os.path.join(DATA, "SNP_21_2020_1.tif")
SHP = os.path.join(DATA, "dead_trees_test.shp")


def main():
    for p in (RGB, SHP):
        if not os.path.exists(p):
            print(f"SKIP: missing {p}")
            return 0
    if not os.environ.get("PYGEOSNAG_ASSETS"):
        print("SKIP: PYGEOSNAG_ASSETS not set")
        return 0
    from pygeosnag.adapt import adapt
    from pygeosnag.detect import detect
    fails = []
    events = []

    def progress(frac, msg):
        events.append(frac)
        return True

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "snags.gpkg")
        n = detect(RGB, out, mode="rgb", points=True, prob_raster=os.path.join(td, "p.tif"),
                   progress=progress, quiet=True)
        ok = os.path.exists(out) and n >= 0 and events and events[-1] == 1.0
        print(f"detect (rgb)        : {n} objects, {len(events)} progress events  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("detect")
        import fiona
        layers = fiona.listlayers(out)
        ok = "snags" in layers and "snag_points" in layers
        print(f"layers              : {layers}  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("layers")

        cancelled = []

        def cancel(frac, msg):
            cancelled.append(frac)
            return False
        try:
            detect(RGB, os.path.join(td, "c.gpkg"), mode="rgb", progress=cancel, quiet=True)
            ok = False
        except RuntimeError as e:
            ok = "cancelled" in str(e)
        print(f"cancel via progress : {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("cancel")

        model = os.path.join(td, "m.joblib")
        adapt([(RGB, SHP, None)], model, mode="rgb", weight=5.0, quiet=True)
        ok = os.path.exists(model) and os.path.exists(os.path.join(td, "m.json"))
        print(f"adapt (36 points)   : {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("adapt")
        n2 = detect(RGB, os.path.join(td, "s2.gpkg"), mode="rgb", model=model, quiet=True)
        print(f"detect with model   : {n2} objects  OK")
    print("ALL OK" if not fails else f"FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
