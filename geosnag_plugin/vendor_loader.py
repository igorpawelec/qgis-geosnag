"""Make the three pure-Python packages importable without installing anything.

``pygeosnag``, ``pygeoadaptels`` and ``pygeopalette`` are pure Python, so a
copy of them rides along inside the plugin (build_zip.py refreshes
``vendor/`` from the sibling checkouts). No pip, no network, no git.

**An installed copy always wins.** The vendored one is a fallback, never an
override; the log line says which one was loaded.

What this does not solve: the packages still need numba, scipy,
scikit-learn, joblib, rasterio, fiona and shapely, which carry binaries and
remain deps.py's job. Copyright (C) 2026 Igor Pawelec. Licence: GPLv3.
"""
import importlib
import importlib.util
import os
import sys

VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor")
VENDORED = ("pygeosnag", "pygeoadaptels", "pygeopalette")


def _spec(name):
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None


def purge_stale():
    """Forget vendored modules already imported from a previous plugin zip.

    Installing a new zip replaces the files under vendor/, but the modules
    imported from the old files stay in sys.modules for the rest of the QGIS
    session, so the operator keeps running last week's package code with
    this week's plugin. Called once on plugin load; only modules whose file
    lies under the vendor directory are dropped, an installed copy is left
    alone. Returns the number of modules dropped.
    """
    root = os.path.abspath(VENDOR_DIR)
    dropped = 0
    for name in list(sys.modules):
        top = name.split(".")[0]
        if top not in VENDORED:
            continue
        mod = sys.modules.get(name)
        origin = getattr(mod, "__file__", None) or ""
        if origin and os.path.abspath(origin).startswith(root):
            del sys.modules[name]
            dropped += 1
    if dropped:
        importlib.invalidate_caches()
    return dropped


def activate(feedback=None):
    """Put the vendored copies on sys.path if the packages are not installed.

    Returns ``name -> "installed" | "vendored" | "missing"``. Safe to call
    repeatedly; never raises.
    """
    status = {}
    need_vendor = False
    for name in VENDORED:
        if _spec(name) is not None:
            status[name] = "installed"
        else:
            need_vendor = True
    if need_vendor and os.path.isdir(VENDOR_DIR):
        if VENDOR_DIR not in sys.path:
            sys.path.append(VENDOR_DIR)
        importlib.invalidate_caches()
    for name in VENDORED:
        if name in status:
            continue
        spec = _spec(name)
        if spec is None:
            status[name] = "missing"
        else:
            origin = getattr(spec, "origin", "") or ""
            status[name] = "vendored" if os.path.abspath(VENDOR_DIR) in os.path.abspath(origin) else "installed"
    if feedback is not None:
        feedback.pushInfo("Packages: " + ", ".join(f"{k} ({v})" for k, v in sorted(status.items())))
    return status


def vendored_versions():
    path = os.path.join(VENDOR_DIR, "VERSIONS.txt")
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    out[k] = v
    except OSError:
        pass
    return out
