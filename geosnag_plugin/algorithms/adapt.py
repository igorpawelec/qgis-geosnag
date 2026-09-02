"""Adapt model -- wraps pygeosnag.adapt.

On the dialog: the raster windows, the dead-tree points, optionally the
rejected objects, and the output model. Mode, band roles, weight and the
models folder sit under Advanced.
"""
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from ._base import (MODE_KEYS, MODES, advanced, package_error, require_packages,
                    set_assets_dir, source_path, warm_jit)


class AdaptModelAlgorithm(QgsProcessingAlgorithm):
    RASTERS = "RASTERS"
    POSITIVES = "POSITIVES"
    NEGATIVES = "NEGATIVES"
    OUTPUT = "OUTPUT"
    # advanced
    MODE = "MODE"
    BANDS = "BANDS"
    WEIGHT = "WEIGHT"
    ASSETS = "ASSETS"

    def name(self):
        return "adapt"

    def displayName(self):
        return "Adapt model"

    def group(self):
        return "Dead trees"

    def groupId(self):
        return "deadtrees"

    def createInstance(self):
        return AdaptModelAlgorithm()

    def shortHelpString(self):
        return (
            "<p>Teach the detector a scene it gets wrong. A forest trained on pine sites "
            "misses what it never saw: on a mountain spruce plot the bleached white snags "
            "scored 0.23 and stayed below the threshold. One labelled window of 53 snags "
            "took it from 6 to 49 of them, and lifted a neighbouring plot from 13 to 21 of "
            "36 without any label of its own.</p>"
            "<p><b>Inputs.</b> One or more raster windows (a few thousand pixels a side at "
            "most), one point layer of dead trees per raster in the same order, and "
            "optionally one point layer per raster of objects you rejected. Every raster "
            "must be in the same band mode.</p>"
            "<p><b>Weight</b> (Advanced): 5 by default, so one small window counts against "
            "the ~2 million rows of the training table.</p>"
            "<p>The result is a .joblib forest to give <i>Detect dead trees</i> as the "
            "adapted model. The training table of the mode (130&ndash;150 MB) comes from the "
            "models folder or the download cache.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.RASTERS, "Raster windows", QgsProcessing.TypeRaster))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.POSITIVES, "Dead trees (points), one layer per raster, same order", QgsProcessing.TypeVectorPoint))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.NEGATIVES, "Rejected objects (points), one layer per raster (optional)",
            QgsProcessing.TypeVectorPoint, optional=True))
        self.addParameter(advanced(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order (empty = default order)", defaultValue="", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.WEIGHT, "Weight of the new rows", QgsProcessingParameterNumber.Double,
            defaultValue=5.0, minValue=0.1)))
        self.addParameter(advanced(QgsProcessingParameterFile(
            self.ASSETS, "Local models folder (remembered; empty = last used or download)",
            behavior=QgsProcessingParameterFile.Folder, optional=True)))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, "Adapted model", fileFilter="joblib (*.joblib)"))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        rasters = self.parameterAsLayerList(parameters, self.RASTERS, context)
        pos = self.parameterAsLayerList(parameters, self.POSITIVES, context)
        neg = self.parameterAsLayerList(parameters, self.NEGATIVES, context) or []
        if len(pos) != len(rasters):
            raise QgsProcessingException("Give one dead-tree point layer per raster, in the same order.")
        if neg and len(neg) != len(rasters):
            raise QgsProcessingException("Give one rejected-objects layer per raster, or none.")
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        set_assets_dir(self.parameterAsFile(parameters, self.ASSETS, context) or None, feedback)
        out = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        windows = [(source_path(r), p.source(), neg[i].source() if neg else None)
                   for i, (r, p) in enumerate(zip(rasters, pos))]

        import contextlib
        import io

        from pygeosnag.adapt import adapt
        buf = io.StringIO()
        feedback.pushInfo("Labelling the windows and refitting the forest; a few minutes.")
        try:
            with contextlib.redirect_stdout(buf):
                adapt(windows, out, mode=mode, bands=bands,
                      weight=self.parameterAsDouble(parameters, self.WEIGHT, context), quiet=False)
        except (RuntimeError, OSError) as e:
            raise package_error(e)
        except Exception as e:
            raise QgsProcessingException(f"{e}\n{buf.getvalue()[-2000:]}")
        for line in buf.getvalue().splitlines():
            if line.strip():
                feedback.pushInfo(line)
        return {self.OUTPUT: out}
