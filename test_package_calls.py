"""Exercise the package calls the algorithms make, WITHOUT QGIS.

Runs pygeosnag.detect (points, with the progress callback the plugin uses,
and a cancel) and pygeosnag.grow_crowns on the SNP_21_2020_1 test raster
shipped with pygeoadaptels -- first on the detected points, then on the
36 reference dead-tree points shipped beside it.

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
    import fiona
    from pygeosnag.detect import detect
    from pygeosnag.grow import grow_crowns
    fails = []
    events = []

    def progress(frac, msg):
        events.append(frac)
        return True

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "trees.gpkg")
        n = detect(RGB, out, mode="rgb", threshold=0.3, prob_raster=os.path.join(td, "p.tif"),
                   progress=progress, quiet=True)
        ok = os.path.exists(out) and n > 0 and events and events[-1] == 1.0
        print(f"detect (rgb, 0.3)   : {n} points, {len(events)} progress events  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("detect")
        with fiona.open(out, layer="dead_trees") as src:
            props = src.schema["properties"]
            ok = src.schema["geometry"] == "Point" and all(k in props for k in ("p", "area_m2", "n_adaptels"))
        print(f"point layer         : {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("layer")

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

        crowns = os.path.join(td, "crowns.gpkg")
        grow_crowns(RGB, out, crowns, mode="rgb", quiet=True)
        with fiona.open(crowns) as src:
            m = len(src)
        ok = os.path.exists(crowns) and m > 0
        print(f"grow (detected pts) : {m} crowns  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("grow")

        crowns2 = os.path.join(td, "crowns_ref.gpkg")
        grow_crowns(RGB, SHP, crowns2, mode="rgb", labels_out=os.path.join(td, "labels.tif"), quiet=True)
        with fiona.open(crowns2) as src:
            m2 = len(src)
        ok = m2 == 36 and os.path.exists(os.path.join(td, "labels.tif"))
        print(f"grow (36 ref pts)   : {m2} crowns + labels  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append("grow_ref")
    print("ALL OK" if not fails else f"FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
