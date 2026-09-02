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
