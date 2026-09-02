"""Style the layers Processing loads back into the project.

Dead-crown polygons get an outline-only style so the orthophoto stays
visible underneath; the probability raster gets a contrast stretch. Every
entry point is wrapped so a styling failure can never fail the run.

Two QGIS traps carried over from the GeoAdaptels + GeoPalette plugin:
post-processor objects must be kept alive after postProcessAlgorithm
returns (parked in ``_KEEP_ALIVE``), and ``layerToLoadOnCompletionDetails``
inserts a default entry for an unknown id, so ``willLoadLayerOnCompletion``
is asked first. Copyright (C) 2026 Igor Pawelec. Licence: GPLv3.
"""
from qgis.core import QgsFillSymbol, QgsProcessingLayerPostProcessorInterface

_KEEP_ALIVE = []


def _usable(layer):
    try:
        return layer is not None and layer.isValid()
    except Exception:
        return False


class PolygonPostProcessor(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, outline="255,220,0,255", width="0.5"):
        super().__init__()
        self._outline = outline
        self._width = width

    def postProcessLayer(self, layer, context, feedback=None):
        if not _usable(layer):
            return
        try:
            symbol = QgsFillSymbol.createSimple({
                "color": "0,0,0,0", "outline_color": self._outline,
                "outline_width": self._width, "outline_style": "solid"})
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()
        except Exception as e:
            if feedback is not None:
                feedback.pushInfo(f"Could not style the polygons: {e}")


class StretchedRasterPostProcessor(QgsProcessingLayerPostProcessorInterface):
    def postProcessLayer(self, layer, context, feedback=None):
        if not _usable(layer):
            return
        try:
            from qgis.core import QgsContrastEnhancement, QgsRasterMinMaxOrigin
            layer.setContrastEnhancement(QgsContrastEnhancement.StretchToMinimumMaximum,
                                         QgsRasterMinMaxOrigin.CumulativeCut)
            layer.triggerRepaint()
        except Exception as e:
            if feedback is not None:
                feedback.pushInfo(f"Could not stretch the raster: {e}")


def _register(context, dest_id, processor):
    try:
        if not dest_id:
            return False
        if hasattr(context, "willLoadLayerOnCompletion"):
            if not context.willLoadLayerOnCompletion(dest_id):
                return False
        details = context.layerToLoadOnCompletionDetails(dest_id)
        if details is None:
            return False
        _KEEP_ALIVE.append(processor)
        details.setPostProcessor(processor)
        return True
    except Exception:
        return False


def style_polygons(context, dest_id, outline="255,220,0,255"):
    return _register(context, dest_id, PolygonPostProcessor(outline=outline))


def style_stretched_raster(context, dest_id):
    return _register(context, dest_id, StretchedRasterPostProcessor())
