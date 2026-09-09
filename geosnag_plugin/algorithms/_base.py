"""Shared helpers for the algorithm classes: the dependency gate, the JIT
warm-up, the progress adapter and the advanced-parameter flag."""
import os

from qgis.core import QgsProcessingException

from ..deps import ensure_dependencies, manual_hint

_WARMED = False
MODES = ["auto: read the band order from the pixels (4 bands = RGB+NIR, 3 bands = CIR or RGB; the log says which)",
         "rgbn: the bands are R, G, B, NIR",
         "cir: the bands are NIR, R, G (colour infrared)",
         "rgb: the bands are R, G, B, no infrared"]
MODE_KEYS = [None, "rgbn", "cir", "rgb"]
SCENE_NORM_OPTIONS = ["auto: normalise as the model was trained (recommended)",
                      "off: raw spectral values (only for a model trained without normalisation)"]
SCENE_NORM_KEYS = ["auto", "off"]
RADIOMETRY_OPTIONS = ["off: the orthophoto as it is (run this first)",
                      "auto: stretch a hazy or flat scene onto the range the model knows, only when it is one",
                      "match: always stretch every band onto that range"]
RADIOMETRY_KEYS = ["off", "auto", "match"]


def hp(param, text):
    """Attach a per-parameter help text (the tooltip / help panel of the dialog, QGIS >= 3.16)."""
    if hasattr(param, "setHelp"):
        param.setHelp(text)
    return param


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
    check_session_packages(feedback)


def check_session_packages(feedback):
    """Log which copy of each bundled package this session actually runs,
    and refuse to run stale code.

    When the plugin's files are replaced under a running QGIS (a zip
    installed, or the folder copied over, without a restart), sys.modules
    keeps the previous version and a run silently uses it: the log then
    claims the new plugin while the old package computes. Seen with 0.4.1:
    the session kept pygeosnag 0.3.0, whose auto band mode read a CIR
    orthophoto as RGB. The version in memory is compared with
    vendor/VERSIONS.txt; a mismatch is an error naming the fix.
    """
    import importlib

    from .. import vendor_loader
    bundled = vendor_loader.vendored_versions()
    root = os.path.abspath(vendor_loader.VENDOR_DIR)
    lines, stale = [], []
    for name in vendor_loader.VENDORED:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:                  # noqa: BLE001 -- reported, not fatal here
            lines.append(f"{name}: not importable ({exc})")
            continue
        origin = os.path.abspath(getattr(mod, "__file__", "") or "")
        ver = str(getattr(mod, "__version__", "?"))
        where = "bundled" if origin.startswith(root) else f"installed, {os.path.dirname(origin)}"
        lines.append(f"{name} {ver} ({where})")
        if where == "bundled" and bundled.get(name) and bundled[name] != ver:
            stale.append(f"{name} {ver} in memory, {bundled[name]} in the plugin folder")
    if feedback is not None:
        feedback.pushInfo("Running: " + ", ".join(lines))
    if stale:
        raise QgsProcessingException(
            "This QGIS session still runs the previous plugin code (" + "; ".join(stale)
            + "). The plugin was updated while QGIS was open; restart QGIS and run again.")


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


def report_models(feedback, threshold, mode=None):
    """Which models a run will use and their operating point (the band mode's own when
    the manifest has one), with a note when the chosen threshold differs from it."""
    try:
        from pygeosnag import assets
        man = assets.manifest(quiet=True)
        opd = man.get("operating_point", {})
        op = float(opd.get("threshold", 0.5))
        per = opd.get("per_mode") or {}
        if mode and mode in per:
            op = float(per[mode])
        feedback.pushInfo(f"Models: {man.get('release', assets.RELEASE)} from {assets.assets_dir()}, operating point p >= {op:g}"
                          f"{' for mode ' + mode if mode and mode in per else ''}"
                          f"{'' if mode else ' (band mode auto: the mode decides, see the first pygeosnag line)'}")
        if threshold is None:
            feedback.pushInfo("Threshold 0: the operating point of the band mode is used")
        elif abs(float(threshold) - op) > 1e-9:
            feedback.pushInfo(f"Threshold {float(threshold):g} differs from the models' operating point {op:g}")
    except Exception as exc:                      # detect fetches the manifest again and reports properly
        feedback.pushInfo(f"Models: manifest not readable yet ({exc})")


def _release():
    try:
        from pygeosnag import assets
        return assets.RELEASE
    except Exception:
        return "assets-v3"


def package_error(e):
    """A pygeosnag RuntimeError as a readable Processing error."""
    msg = str(e)
    if any(k in msg for k in ("could not download", "HTTP Error", "URLError", "urlopen", "Not Found")):
        msg += ("\n\nThe models could not be downloaded (the pygeosnag GitHub release is not published "
                "yet, or the machine is offline). Copy manifest.json and the model files into "
                f"{os.path.join(os.path.expanduser('~'), '.cache', 'pygeosnag', _release())} -- that is "
                "where pygeosnag looks without any setting -- or open Advanced and set 'Local models "
                "folder' to the folder that holds them; it is remembered for later runs.")
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
