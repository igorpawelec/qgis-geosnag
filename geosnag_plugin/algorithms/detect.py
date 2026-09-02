"""Detect dead trees -- wraps pygeosnag.detect.

Five things on the dialog: the orthophoto, the band mode, the threshold, an
optional stand layer and the output. Everything else sits under Advanced
with the values the research calibrated; nobody running this on an
orthophoto should have to think about tile sizes.
"""
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
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
    OBJECT_STAGE = "OBJECT_STAGE"
    OBJECT_THRESHOLD = "OBJECT_THRESHOLD"
    MIN_AREA = "MIN_AREA"
    POINTS = "POINTS"
    MODEL = "MODEL"
    ASSETS = "ASSETS"
    TILE = "TILE"
    OVERLAP = "OVERLAP"
    EDGE_PX = "EDGE_PX"
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
            "<p>Standing dead trees from an orthophoto, no seeds or tree tops needed: "
            "adaptel micro-segmentation, twenty spectral and contextual features per "
            "adaptel, a random forest trained on seven Polish forest sites, an absolute "
            "probability threshold, and merging of adjacent detections into crown "
            "polygons.</p>"
            "<p><b>Band mode.</b> Auto takes 4 bands as R, G, B, NIR and 3 bands as R, G, B. "
            "A CIR orthophoto looks like any 3-band raster, so choose <i>cir</i> for it.</p>"
            "<p><b>Threshold.</b> 0.5 is the calibrated default; 0.4&ndash;0.6 is the useful "
            "range. Lower finds more and includes more false objects.</p>"
            "<p><b>Stand polygons.</b> Optional. Forest-management polygons with a stand age "
            "field (<code>species_age</code>): stands of at least 10 years, shrunk by 2 m, "
            "keep their objects. On seven sites this removed a quarter of the objects and, "
            "in a field review, only roads and fields.</p>"
            "<p><b>Advanced</b> holds the rest: band roles for an unusual band order, the "
            "mask's age and buffer, the object forest, a centroid layer, an adapted model "
            "from <i>Adapt model</i>, and the local models folder (needed while the models "
            "are not yet published as a GitHub release; remembered once given).</p>"
            "<p>What to expect, with the site under test never seen in training: recall "
            "about 65%, precision 31% against an incomplete reference and roughly "
            "55&ndash;75% after a field review; RGB and CIR about 15% below RGB+NIR. A scene "
            "from a different camera, species or decay stage can transfer badly: label a few "
            "objects and use <i>Adapt model</i>.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto"))
        self.addParameter(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, "Probability threshold (0.5 calibrated; 0.4-0.6 useful)",
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
            self.KEEP_OUTSIDE, "Mask: keep objects outside, flagged in_stands = 0", defaultValue=False)))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.OBJECT_STAGE, "Score objects with the object forest (RGB+NIR only)", defaultValue=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.OBJECT_THRESHOLD, "Drop objects below this object probability (0 = keep all)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0, maxValue=1.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MIN_AREA, "Minimum object area (m2)", QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.POINTS, "Also write a centroid layer (snag_points, same GeoPackage)", defaultValue=True)))
        self.addParameter(advanced(QgsProcessingParameterFile(
            self.MODEL, "Adapted model (.joblib from Adapt model)", optional=True, fileFilter="joblib (*.joblib)")))
        self.addParameter(advanced(QgsProcessingParameterFile(
            self.ASSETS, "Local models folder (remembered; empty = last used or download)",
            behavior=QgsProcessingParameterFile.Folder, optional=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.TILE, "Tile size (px at 0.25 m)", QgsProcessingParameterNumber.Integer, defaultValue=2400, minValue=600)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.OVERLAP, "Tile overlap (px)", QgsProcessingParameterNumber.Integer, defaultValue=200, minValue=50)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.EDGE_PX, "Flag objects closer than this to nodata (px)", QgsProcessingParameterNumber.Integer,
            defaultValue=8, minValue=0)))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Dead crowns", type=QgsProcessing.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.PROB, "Probability raster", optional=True, createByDefault=False))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        raster_path = source_path(layer)
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)
        stands_layer = self.parameterAsVectorLayer(parameters, self.STANDS, context)
        stands = stand_layer = None
        if stands_layer is not None:
            src = stands_layer.source()
            stands = src.split("|", 1)[0]
            for part in src.split("|")[1:]:
                if part.startswith("layername="):
                    stand_layer = part[len("layername="):]
        model = self.parameterAsFile(parameters, self.MODEL, context) or None
        set_assets_dir(self.parameterAsFile(parameters, self.ASSETS, context) or None, feedback)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if not out.lower().endswith(".gpkg"):
            raise QgsProcessingException("The output must be a GeoPackage (.gpkg): pygeosnag writes it directly.")
        prob = self.parameterAsOutputLayer(parameters, self.PROB, context) or None
        obj_thr = self.parameterAsDouble(parameters, self.OBJECT_THRESHOLD, context)
        points = self.parameterAsBool(parameters, self.POINTS, context)

        from pygeosnag.detect import detect
        try:
            n = detect(raster_path, out, mode=mode, bands=bands, threshold=threshold,
                       min_area=self.parameterAsDouble(parameters, self.MIN_AREA, context),
                       tile=self.parameterAsInt(parameters, self.TILE, context),
                       overlap=self.parameterAsInt(parameters, self.OVERLAP, context),
                       stands=stands, stand_layer=stand_layer,
                       stand_age=self.parameterAsDouble(parameters, self.STAND_AGE, context),
                       stand_buffer=self.parameterAsDouble(parameters, self.STAND_BUFFER, context),
                       keep_outside=self.parameterAsBool(parameters, self.KEEP_OUTSIDE, context),
                       object_stage=self.parameterAsBool(parameters, self.OBJECT_STAGE, context),
                       object_threshold=obj_thr if obj_thr > 0 else None,
                       prob_raster=prob, points=points,
                       edge_px=self.parameterAsInt(parameters, self.EDGE_PX, context),
                       model=model, progress=progress_adapter(feedback), quiet=True)
        except RuntimeError as e:
            if "cancelled" in str(e):
                return {}
            raise package_error(e)
        except (ValueError, OSError) as e:
            raise QgsProcessingException(str(e))
        feedback.pushInfo(f"{n} dead-crown objects")
        styling.style_polygons(context, out)
        if points:
            context.addLayerToLoadOnCompletion(
                f"{out}|layername=snag_points",
                QgsProcessingContext.LayerDetails("snag_points", context.project(), "POINTS"))
        if prob:
            styling.style_stretched_raster(context, prob)
        result = {self.OUTPUT: out}
        if prob:
            result[self.PROB] = prob
        return result
