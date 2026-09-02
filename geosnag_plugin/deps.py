"""Dependency bootstrap -- the single highest-risk piece of this plugin.

QGIS ships its own Python, and things have to be importable *from that
interpreter*. The three pure-Python packages (pygeosnag, pygeoadaptels,
pygeopalette) ride along inside the plugin (see ``vendor_loader``), so this
module only ever has to fetch the ones that carry compiled binaries.

Lessons carried over from the GeoAdaptels + GeoPalette plugin, learned
against QGIS 3.40/3.44 (Python 3.12) on Windows:

1. ``sys.executable`` is a launcher, not the interpreter (``bin/python3.exe``
   does not initialise as a subprocess); the real one sits at ``sys.prefix``.
2. Recent rasterio/fiona drag in numpy 2.x, which breaks numba and scipy
   on the numpy 1.26 that QGIS ships; the installs are pinned to keep the
   interpreter's numpy.
3. pip's real error is captured and reported, not swallowed.
4. PEP 668 externally-managed interpreters are retried with
   ``--break-system-packages``.

Policy: auto-install on first use, with the exact manual command in the log
if it fails. Copyright (C) 2026 Igor Pawelec. Licence: GPLv3.
"""
import importlib
import importlib.util
import os
import subprocess
import sys

# module name -> pip name. The vendored pure-Python packages are checked but
# never handed to pip.
REQUIRED = {
    "pygeosnag": None, "pygeoadaptels": None, "pygeopalette": None,
    "numba": "numba", "scipy": "scipy", "sklearn": "scikit-learn", "joblib": "joblib",
    "rasterio": "rasterio", "fiona": "fiona", "shapely": "shapely",
}


def _install_specs(modules=None):
    """pip specs for the binary dependencies, pinned to the interpreter's numpy line."""
    try:
        import numpy
        numpy_major = int(numpy.__version__.split(".")[0])
    except Exception:
        numpy_major = 1
    pins = {"rasterio": "rasterio<1.4", "fiona": "fiona<1.10", "numpy": "numpy<2"} if numpy_major < 2 else {}
    wanted = [m for m in (modules or REQUIRED) if REQUIRED.get(m)]
    specs = [pins.get(REQUIRED[m], REQUIRED[m]) for m in wanted]
    if numpy_major < 2 and specs:
        specs.append(pins["numpy"])            # keep pip from upgrading numpy underneath numba
    return specs


def _qgis_python():
    names = ("python.exe", "python3.exe", "python3", "python")
    for base in (sys.prefix, os.path.join(sys.prefix, "bin")):
        for name in names:
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
    return sys.executable


def missing_packages():
    out = []
    for m in REQUIRED:
        try:
            if importlib.util.find_spec(m) is None:
                out.append(m)
        except (ImportError, ValueError):
            out.append(m)
    return out


def _pip(py, specs, extra=()):
    cmd = [py, "-m", "pip", "install", "--user", *extra, *specs]
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_dependencies(feedback=None, auto_install=True):
    """Return ``(ok, missing)``. Never raises; never hard-crashes the plugin."""
    from . import vendor_loader
    vendor_loader.activate(feedback)

    missing = missing_packages()
    if not missing:
        return True, []
    if not auto_install:
        return False, missing

    to_install = [m for m in missing if REQUIRED.get(m)]
    vendored_missing = [m for m in missing if not REQUIRED.get(m)]
    if vendored_missing and feedback is not None:
        feedback.reportError(
            "These are bundled with the plugin but did not import: "
            + ", ".join(vendored_missing)
            + ". The plugin's vendor/ folder looks incomplete -- reinstall the plugin zip.")
    if not to_install:
        return False, missing

    py = _qgis_python()
    specs = _install_specs(to_install)
    if feedback is not None:
        feedback.pushInfo(f"Installing {', '.join(specs)} using {py}")
    try:
        r = _pip(py, specs)
        if r.returncode != 0 and "externally-managed-environment" in ((r.stderr or "") + (r.stdout or "")):
            if feedback is not None:
                feedback.pushInfo("Interpreter is externally managed; retrying with --break-system-packages.")
            r = _pip(py, specs, extra=("--break-system-packages",))
    except Exception as e:  # pragma: no cover - environment dependent
        if feedback is not None:
            feedback.reportError(f"Could not launch pip: {e}\n{manual_hint()}")
        return False, missing

    if r.returncode != 0:
        if feedback is not None:
            tail = (r.stdout or "")[-2000:] + "\n" + (r.stderr or "")[-2000:]
            feedback.reportError("pip failed:\n" + tail.strip()
                                 + "\n\nInstall by hand into QGIS's Python and restart QGIS:\n  " + manual_hint())
        return False, missing

    importlib.invalidate_caches()
    still = missing_packages()
    if still and feedback is not None:
        feedback.reportError("pip reported success but these are still not importable: "
                             + ", ".join(still) + ".\nRestart QGIS, then try again.")
    return (not still), still


def manual_hint():
    py = _qgis_python()
    return f'"{py}" -m pip install --user ' + " ".join(_install_specs())
