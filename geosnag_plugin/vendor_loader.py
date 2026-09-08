"""Make the three pure-Python packages importable without installing anything.

``pygeosnag``, ``pygeoadaptels`` and ``pygeopalette`` are pure Python, so a
copy of them rides along inside the plugin (build_zip.py refreshes
``vendor/`` from the sibling checkouts). No pip, no network, no git.

**An installed copy wins unless the bundled one is newer.** Another plugin
that loaded earlier (GeoAdaptels + GeoPalette, alphabetically first) puts
its own vendor/ on sys.path, and QGIS then imports *its* pygeoadaptels for
every plugin in the session -- seen with 0.4.5: the pocket-filling fix of
pygeoadaptels 0.10.4 bundled here never ran because 0.10.3 from the other
plugin was already importable. So a package that is importable from
elsewhere at a version older than VERSIONS.txt is replaced: our vendor/
goes to the front of sys.path and the stale modules are dropped from
sys.modules before anything imports them. The log line says which copy
won and from where.

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
# The binary dependencies deps.py installs, private to this plugin (never the
# user site, which every Python of the same minor version on the machine
# reads -- see deps.py).
LIBS_DIR = os.path.join(os.path.dirname(__file__), "libs")


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


def _version_tuple(text):
    out = []
    for part in str(text).strip().split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _version_of(spec):
    """The __version__ literal in a package's __init__.py (the last one, which
    is the no-metadata fallback the packages keep in step with pyproject)."""
    import re
    try:
        with open(spec.origin, encoding="utf-8") as fh:
            found = re.findall(r'__version__\s*=\s*"([^"]+)"', fh.read())
        return found[-1] if found else "0"
    except OSError:
        return "0"


def activate(feedback=None):
    """Put the vendored copies on sys.path; prefer them when they are newer.

    Returns ``name -> "installed" | "vendored" | "missing"``. Safe to call
    repeatedly; never raises.
    """
    status = {}
    # The plugin-private binary dependencies. Appended, so anything QGIS's own
    # Python already provides keeps winning.
    if os.path.isdir(LIBS_DIR) and LIBS_DIR not in sys.path:
        sys.path.append(LIBS_DIR)
        importlib.invalidate_caches()
    need_vendor = False
    root = os.path.abspath(VENDOR_DIR)
    bundled = vendored_versions()
    prefer_ours = []
    for name in VENDORED:
        spec = _spec(name)
        if spec is not None:
            origin = getattr(spec, "origin", "") or ""
            if root in os.path.abspath(origin):
                status[name] = "vendored"
            elif bundled.get(name) and _version_tuple(_version_of(spec)) < _version_tuple(bundled[name]):
                prefer_ours.append((name, _version_of(spec), bundled[name], origin))
            else:
                status[name] = "installed"
        else:
            need_vendor = True
    if prefer_ours and os.path.isdir(VENDOR_DIR):
        # our copy is newer than the one another plugin (or an old install)
        # made importable: front of the path, stale modules out
        for name, old, new, origin in prefer_ours:
            for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
                del sys.modules[mod]
            if feedback is not None:
                feedback.pushInfo(f"{name}: {old} at {os.path.dirname(origin)} replaced by the bundled {new}")
        if VENDOR_DIR in sys.path:
            sys.path.remove(VENDOR_DIR)
        sys.path.insert(0, VENDOR_DIR)
        importlib.invalidate_caches()
        for name, *_ in prefer_ours:
            status[name] = "vendored"
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
