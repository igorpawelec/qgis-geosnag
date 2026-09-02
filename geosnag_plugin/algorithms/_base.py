"""Shared helpers for the algorithm classes: the dependency gate, the JIT
warm-up, the progress adapter and the advanced-parameter flag."""
import os

from qgis.core import QgsProcessingException

from ..deps import ensure_dependencies, manual_hint

_WARMED = False
MODES = ["auto (4 bands = RGB+NIR, 3 bands = RGB)", "rgbn (R, G, B, NIR)", "cir (NIR, R, G)", "rgb (R, G, B)"]
MODE_KEYS = [None, "rgbn", "cir", "rgb"]


def warm_jit(feedback=None):
    """Compile the adaptel kernels here, on the main thread.

    **Call this from prepareAlgorithm, never from processAlgorithm.**
    pygeoadaptels computes inside ``@njit(cache=True)`` functions; compiling
    them on the worker thread Processing runs on takes QGIS down with an
    access violation, and installing the plugin from a zip wipes the compiled
    cache, so every update arms that crash. ``prepareAlgorithm`` runs on the
    main thread before the task starts. Runs once per session, never fatal.
    """
    global _WARMED
    if _WARMED:
        return
    try:
        import contextlib
        import io

        import numpy as np

        from pygeoadaptels import adaptels_from_array
    except Exception:
        return
    if feedback is not None:
        feedback.pushInfo("Preparing the compute kernels (first run after an update only)...")
    data = np.zeros((3, 8, 8), dtype=np.float64)
    data[:, 2:5, 2:5] = 100.0
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            adaptels_from_array(data, threshold=10.0)
    except Exception as exc:
        if feedback is not None:
            feedback.pushInfo(f"Kernel warm-up skipped: {exc}")
    _WARMED = True


def require_packages(feedback):
    ok, missing = ensure_dependencies(feedback)
    if not ok:
        raise QgsProcessingException(
            "This algorithm needs the Python packages: " + ", ".join(missing)
            + ".\nInstall them into QGIS's own Python and restart QGIS:\n  " + manual_hint())


SETTINGS_KEY = "geosnag/assets_dir"


def set_assets_dir(path, feedback=None):
    """Point pygeosnag at a local model directory instead of the download cache.

    A folder given once is remembered in the QGIS settings, so the parameter
    can stay empty on later runs. Order: the parameter, then the remembered
    folder, then whatever PYGEOSNAG_ASSETS already says, then the download
    cache (which needs the GitHub release to exist).
    """
    try:
        from qgis.core import QgsSettings
        settings = QgsSettings()
    except Exception:
        settings = None
    if path:
        if settings is not None:
            settings.setValue(SETTINGS_KEY, path)
    elif settings is not None:
        saved = settings.value(SETTINGS_KEY, "", type=str)
        if saved and os.path.isdir(saved):
            path = saved
    if path:
        os.environ["PYGEOSNAG_ASSETS"] = path
        if feedback is not None:
            feedback.pushInfo(f"Models from {path}")
    elif feedback is not None:
        feedback.pushInfo("Models from the download cache (the pygeosnag GitHub release); "
                          "give a local models folder under Advanced if that fails.")
    return path


def package_error(e):
    """A pygeosnag RuntimeError as a readable Processing error."""
    msg = str(e)
    if "could not download" in msg:
        msg += ("\n\nIn QGIS: open Advanced and set 'Local models folder' to the folder that holds "
                "manifest.json and the segments_*.joblib files. It is remembered for later runs.")
    return QgsProcessingException(msg)


def progress_adapter(feedback):
    """pygeosnag's progress callback wired to the Processing feedback.

    Returning False cancels the run inside the package, which raises; the
    algorithm turns that into a clean Processing cancel.
    """
    def cb(fraction, message):
        try:
            feedback.setProgress(int(round(100 * float(fraction))))
            if message:
                feedback.pushInfo(message)
        except Exception:
            pass
        return not feedback.isCanceled()
    return cb


def source_path(layer):
    """File path of a layer's source, without the ``|layername=`` suffix
    pygeosnag cannot open (rasters) -- vector sources keep it, pygeosnag's
    point reader understands it."""
    src = layer.source()
    if "|" in src:
        src = src.split("|", 1)[0]
    return src


def advanced(param):
    try:
        from qgis.core import QgsProcessingParameterDefinition
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
    except Exception:
        pass
    return param
