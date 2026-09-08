"""Style the layers Processing loads back into the project -- through
Processing's own output-style registry, with QML files shipped in styles/.

Until 0.4.6 the plugin styled its results with
``QgsProcessingLayerPostProcessorInterface`` subclasses: Python that runs
on the GUI thread inside ``QgsProcessingAlgRunnerTask::finished``, after
the algorithm task has been torn down. QGIS died there twice with an access
violation -- once in 0.3.1 (a raster contrast stretch scanning every pixel
of a full orthophoto) and once with 0.4.6 after Grow crowns on a
150-megapixel orthophoto (15 000 polygons, the output file complete). Both
times the plugin's only code on that path was the styling.

Processing has a registry for exactly this: ``RenderingStyles`` maps an
algorithm id and an output name to a QML file, and ``post_process_layer``
(processing/gui/Postprocessing.py) calls ``layer.loadNamedStyle`` on it
itself, before any post-processor. So the plugin registers its three QML
files at load and again before each run (the registry is in memory; a
Processing restart empties it), and no plugin code runs when a task
completes. The ``style_*`` entry points are kept for the algorithms and
now only make sure the registration is in place.
Copyright (C) 2026 Igor Pawelec. Licence: GPLv3.
"""
import os

STYLES_DIR = os.path.join(os.path.dirname(__file__), "styles")
# algorithm id -> {output name: QML file}
OUTPUT_STYLES = {
    "geosnag:detect": {"OUTPUT": "points.qml", "PROB": "probability.qml"},
    "geosnag:grow": {"OUTPUT": "crowns.qml"},
}


def register_output_styles(feedback=None):
    """Put the plugin's QML files into Processing's RenderingStyles registry
    (in memory only -- nothing is written to the user's settings). Never raises."""
    try:
        from processing.gui.RenderingStyles import RenderingStyles
    except Exception:                             # noqa: BLE001 -- Processing absent (tests, headless)
        return False
    try:
        for alg, outputs in OUTPUT_STYLES.items():
            entry = RenderingStyles.styles.setdefault(alg, {})
            for out, qml in outputs.items():
                path = os.path.join(STYLES_DIR, qml)
                if os.path.exists(path):
                    entry[out] = path
        return True
    except Exception as exc:                      # noqa: BLE001
        if feedback is not None:
            feedback.pushInfo(f"Output styles not registered: {exc}")
        return False


def style_polygons(context, dest_id, outline=None):
    return register_output_styles()


def style_points(context, dest_id):
    return register_output_styles()


def style_scored(context, dest_id):
    return register_output_styles()


def style_stretched_raster(context, dest_id):
    return register_output_styles()
