"""Style the layers Processing loads back into the project.

Dead-crown polygons get an outline-only style so the orthophoto stays
visible underneath; the probability raster gets a contrast stretch. Every
entry point is wrapped so a styling failure can never fail the run.

Two QGIS traps carried over from the GeoAdaptels + GeoPalette plugin:
a post-processor must not be garbage-collected before the layer is loaded,
and ``layerToLoadOnCompletionDetails`` inserts a default entry for an
unknown id, so ``willLoadLayerOnCompletion`` is asked first.

On the first trap the older plugin was wrong, and this one inherited it.
``LayerDetails.setPostProcessor`` says "Ownership of processor is
transferred", and on QGIS 3.44 it is: ``sip.ispyowned`` goes from True to
False across the call. Parking every processor in a module-level list that
is never emptied therefore kept one dead object per algorithm run for the
rest of the QGIS session. The reference is now kept only if ownership did
*not* transfer, and only until the run that needs it is over.
Copyright (C) 2026 Igor Pawelec. Licence: GPLv3.
"""
from qgis.core import QgsFillSymbol, QgsProcessingLayerPostProcessorInterface

# Only for a QGIS whose bindings do not take ownership; emptied on each run.
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


class ProbabilityPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Fixed 0-1 pseudocolour for the probability raster. No statistics.

    The first version stretched the raster with a cumulative cut, which
    scans every pixel -- on the GUI thread, inside the task-completion
    handler. On a full orthophoto (130 M pixels) that pass let Qt re-enter
    the event loop while the finished task was being torn down: an access
    violation in on_complete, not a catchable error. The probability is
    known to lie in 0-1 (nodata -1), so the ramp is set explicitly and
    nothing is read here.
    """

    def postProcessLayer(self, layer, context, feedback=None):
        if not _usable(layer):
            return
        try:
            from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
            from qgis.PyQt.QtGui import QColor
            ramp = QgsColorRampShader(0.0, 1.0)
            ramp.setColorRampType(QgsColorRampShader.Interpolated)
            ramp.setColorRampItemList([
                QgsColorRampShader.ColorRampItem(0.0, QColor(0, 0, 0, 0), "0"),
                QgsColorRampShader.ColorRampItem(0.3, QColor(255, 255, 150, 90), "0.3"),
                QgsColorRampShader.ColorRampItem(0.5, QColor(255, 200, 0, 170), "0.5"),
                QgsColorRampShader.ColorRampItem(0.7, QColor(255, 120, 0, 210), "0.7"),
                QgsColorRampShader.ColorRampItem(1.0, QColor(220, 0, 0, 240), "1"),
            ])
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(ramp)
            renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
            renderer.setClassificationMin(0.0)
            renderer.setClassificationMax(1.0)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
        except Exception as e:
            if feedback is not None:
                feedback.pushInfo(f"Could not style the probability raster: {e}")


StretchedRasterPostProcessor = ProbabilityPostProcessor


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
        del _KEEP_ALIVE[:]                       # last run's, if any
        details.setPostProcessor(processor)
        if _still_ours(processor):               # bindings without /Transfer/
            _KEEP_ALIVE.append(processor)
        return True
    except Exception:
        return False


def _still_ours(processor):
    """True when Python, not C++, owns the processor after the hand-over."""
    try:
        from qgis.PyQt import sip
        return bool(sip.ispyowned(processor))
    except Exception:
        return True                              # cannot tell: keep it, as before


class ScoredPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Adaptels coloured by their probability, half-transparent, thin outline.

    Four fixed classes rather than a data-driven ramp, so the colours mean
    the same thing on every scene: below 0.3 faint, 0.3-0.5 yellow, 0.5-0.7
    orange, 0.7 and up red. The layer is meant to be looked at over the
    orthophoto, hence the transparency.
    """

    CLASSES = [(0.0, 0.3, "255,255,150,70", "< 0.3"), (0.3, 0.5, "255,220,0,140", "0.3 - 0.5"),
               (0.5, 0.7, "255,140,0,170", "0.5 - 0.7"), (0.7, 1.0001, "230,0,0,200", ">= 0.7")]

    def postProcessLayer(self, layer, context, feedback=None):
        if not _usable(layer):
            return
        try:
            from qgis.core import QgsGraduatedSymbolRenderer, QgsRendererRange
            ranges = []
            for lo, hi, colour, label in self.CLASSES:
                sym = QgsFillSymbol.createSimple({"color": colour, "outline_color": "80,80,80,120",
                                                  "outline_width": "0.15", "outline_style": "solid"})
                ranges.append(QgsRendererRange(lo, hi, sym, label))
            layer.setRenderer(QgsGraduatedSymbolRenderer("p", ranges))
            layer.triggerRepaint()
        except Exception as e:
            if feedback is not None:
                feedback.pushInfo(f"Could not style the scored adaptels: {e}")


class PointPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Dead-tree points: a hollow yellow circle, so the crown underneath stays visible."""

    def postProcessLayer(self, layer, context, feedback=None):
        if not _usable(layer):
            return
        try:
            from qgis.core import QgsMarkerSymbol
            symbol = QgsMarkerSymbol.createSimple({
                "name": "circle", "color": "0,0,0,0", "outline_color": "255,220,0,255",
                "outline_width": "0.6", "size": "3.2"})
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()
        except Exception as e:
            if feedback is not None:
                feedback.pushInfo(f"Could not style the points: {e}")


def style_polygons(context, dest_id, outline="255,220,0,255"):
    return _register(context, dest_id, PolygonPostProcessor(outline=outline))


def style_points(context, dest_id):
    return _register(context, dest_id, PointPostProcessor())


def style_scored(context, dest_id):
    return _register(context, dest_id, ScoredPostProcessor())


def style_stretched_raster(context, dest_id):
    return _register(context, dest_id, StretchedRasterPostProcessor())
