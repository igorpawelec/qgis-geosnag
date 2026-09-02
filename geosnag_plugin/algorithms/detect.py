"""Detect dead trees -- wraps pygeosnag.detect. One point per dead tree.

Five things on the dialog: the orthophoto, the band mode, the threshold,
an optional stand layer and the output. The rest sits under Advanced with
the values the research calibrated.
"""
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
)

from .. import styling
from ._base import (MODE_KEYS, MODES, advanced, package_error, progress_adapter,
                    require_packages, set_assets_dir, source_path, warm_jit)


def _split_source(layer):
    src = layer.source()
    path = src.split("|", 1)[0]
    name = None
    for part in src.split("|")[1:]:
        if part.startswith("layername="):
            name = part[len("layername="):]
    return path, name


class DetectDeadTreesAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    MODE = "MODE"
    THRESHOLD = "THRESHOLD"
    STANDS = "STANDS"
    OUTPUT = "OUTPUT"
    # advanced
    BANDS = "BANDS"
    STAND_AGE = "STAND_AGE"
    STAND_BUFFER = "STAND_BUFFER"
    KEEP_OUTSIDE = "KEEP_OUTSIDE"
    SUPPRESS = "SUPPRESS"
    ASSETS = "ASSETS"
    PROB = "PROB"

    def name(self):
        return "detect"

    def displayName(self):
        return "Detect dead trees"

    def group(self):
        return "Dead trees"

    def groupId(self):
        return "deadtrees"

    def createInstance(self):
        return DetectDeadTreesAlgorithm()

    def shortHelpString(self):
        return (
            "<p>One point per standing dead tree, from the orthophoto alone: adaptel "
            "micro-segmentation, twenty spectral and contextual features per adaptel, a "
            "random forest trained on seven Polish forest sites, a probability threshold, "
            "adjacent detections merged and their centroid taken as the point. The points are "
            "seeds for <i>Grow crowns</i>.</p>"
            "<p><b>Band mode.</b> Auto takes 4 bands as R, G, B, NIR and 3 bands as R, G, B. "
            "A CIR orthophoto looks like any 3-band raster, so choose <i>cir</i> for it.</p>"
            "<p><b>Threshold.</b> 0.5 is calibrated on the training sites; 0.4&ndash;0.6 is "
            "the useful range. On a scene the model has not seen (another camera, species or "
            "decay stage) the ranking is usually right and the scale is not: lower it.</p>"
            "<p><b>Stand polygons.</b> Optional. Forest-management polygons with a stand age "
            "field (<code>species_age</code>): points inside stands of at least 10 years, "
            "shrunk by 2 m, are kept; roads and fields fall out.</p>"
            "<p>Measured with the site under test never seen in training: recall 63%, "
            "precision 33% against an incomplete reference and 55&ndash;75% after a field "
            "review; points a median 0.47 m from the reference top.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto"))
        self.addParameter(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, "Probability threshold (0.5 calibrated; lower on an unfamiliar scene)",
            QgsProcessingParameterNumber.Double, defaultValue=0.5, minValue=0.05, maxValue=0.95))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.STANDS, "Stand polygons (optional mask)", [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order, e.g. nir,red,green,blue (empty = default)",
            defaultValue="", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.STAND_AGE, "Mask: minimum stand age (years)", QgsProcessingParameterNumber.Double,
            defaultValue=10.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.STAND_BUFFER, "Mask: buffer (m, negative shrinks)", QgsProcessingParameterNumber.Double,
            defaultValue=-2.0)))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.KEEP_OUTSIDE, "Mask: keep points outside, flagged in_stands = 0", defaultValue=False)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.SUPPRESS, "Drop the weaker of two points closer than (m)", QgsProcessingParameterNumber.Double,
            defaultValue=3.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterFile(
            self.ASSETS, "Local models folder (remembered; empty = last used or download)",
            behavior=QgsProcessingParameterFile.Folder, optional=True)))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Dead trees", type=QgsProcessing.TypeVectorPoint))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.PROB, "Probability raster", optional=True, createByDefault=False))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        stands_layer = self.parameterAsVectorLayer(parameters, self.STANDS, context)
        stands, stand_layer = _split_source(stands_layer) if stands_layer is not None else (None, None)
        set_assets_dir(self.parameterAsFile(parameters, self.ASSETS, context) or None, feedback)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if not out.lower().endswith(".gpkg"):
            raise QgsProcessingException("The output must be a GeoPackage (.gpkg): pygeosnag writes it directly.")
        prob = self.parameterAsOutputLayer(parameters, self.PROB, context) or None
        from pygeosnag.detect import detect
        try:
            n = detect(source_path(layer), out, mode=mode, bands=bands,
                       threshold=self.parameterAsDouble(parameters, self.THRESHOLD, context),
                       suppress_m=self.parameterAsDouble(parameters, self.SUPPRESS, context),
                       stands=stands, stand_layer=stand_layer,
                       stand_age=self.parameterAsDouble(parameters, self.STAND_AGE, context),
                       stand_buffer=self.parameterAsDouble(parameters, self.STAND_BUFFER, context),
                       keep_outside=self.parameterAsBool(parameters, self.KEEP_OUTSIDE, context),
                       prob_raster=prob, progress=progress_adapter(feedback), quiet=True)
        except RuntimeError as e:
            if "cancelled" in str(e):
                return {}
            raise package_error(e)
        except (ValueError, OSError) as e:
            raise package_error(e)
        feedback.pushInfo(f"{n} dead trees")
        styling.style_points(context, out)
        if prob:
            styling.style_stretched_raster(context, prob)
        result = {self.OUTPUT: out}
        if prob:
            result[self.PROB] = prob
        return result
