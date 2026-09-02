"""Grow crowns -- wraps pygeosnag.grow_crowns (pygeoadaptels' seeded region
growing with the crown recipe)."""
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
)

from .. import styling
from ._base import MODE_KEYS, MODES, advanced, package_error, require_packages, source_path, warm_jit


class GrowCrownsAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    POINTS = "POINTS"
    OUTPUT = "OUTPUT"
    # advanced
    MODE = "MODE"
    BANDS = "BANDS"
    MAX_COST = "MAX_COST"
    MAX_RADIUS = "MAX_RADIUS"
    WEIGHTS = "WEIGHTS"
    FILL_HOLES = "FILL_HOLES"
    LABELS = "LABELS"

    def name(self):
        return "grow"

    def displayName(self):
        return "Grow crowns"

    def group(self):
        return "Dead trees"

    def groupId(self):
        return "deadtrees"

    def createInstance(self):
        return GrowCrownsAlgorithm()

    def shortHelpString(self):
        return (
            "<p>Grow the dead-tree points into crown polygons: every point grows into the "
            "region that looks like the pixel it sits on, on CIELAB, with a spectral tolerance "
            "and a radius cap (pygeoadaptels' seeded region growing, inverse OBIA).</p>"
            "<p>The recipe under Advanced was worked out on a spruce plot with bleached snags: "
            "a* weighted 2.5 (the red-green axis separates grey-white crowns from green "
            "canopy), Delta-E tolerance 15, at most 20 px (5 m at 0.25 m) from the seed, holes "
            "inside a crown filled. Points can also come from anywhere else &mdash; a click, a "
            "field survey &mdash; as long as they sit on the crown.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Dead trees (points)", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(advanced(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order (empty = default order)", defaultValue="", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MAX_COST, "Spectral tolerance (Delta-E)", QgsProcessingParameterNumber.Double,
            defaultValue=15.0, minValue=1.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MAX_RADIUS, "Maximum radius from the seed (px)", QgsProcessingParameterNumber.Integer,
            defaultValue=20, minValue=2)))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.WEIGHTS, "Band weights L,a,b", defaultValue="0.5,2.5,1.0")))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.FILL_HOLES, "Fill holes inside crowns", defaultValue=True)))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Crowns", type=QgsProcessing.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.LABELS, "Label raster", optional=True, createByDefault=False))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        pts = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        try:
            weights = tuple(float(x) for x in self.parameterAsString(parameters, self.WEIGHTS, context).split(","))
            if len(weights) != 3:
                raise ValueError
        except ValueError:
            raise QgsProcessingException("Band weights must be three numbers, e.g. 0.5,2.5,1.0")
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if not out.lower().endswith(".gpkg"):
            raise QgsProcessingException("The output must be a GeoPackage (.gpkg): pygeosnag writes it directly.")
        labels = self.parameterAsOutputLayer(parameters, self.LABELS, context) or None
        from pygeosnag.grow import grow_crowns
        feedback.pushInfo("Converting to CIELAB and growing the points; a minute or two.")
        try:
            grow_crowns(source_path(layer), pts.source(), out, mode=mode, bands=bands, labels_out=labels,
                        max_cost=self.parameterAsDouble(parameters, self.MAX_COST, context),
                        band_weights=weights,
                        max_radius=self.parameterAsInt(parameters, self.MAX_RADIUS, context),
                        fill_holes=self.parameterAsBool(parameters, self.FILL_HOLES, context), quiet=True)
        except (RuntimeError, ValueError, OSError) as e:
            raise package_error(e)
        styling.style_polygons(context, out)
        result = {self.OUTPUT: out}
        if labels:
            result[self.LABELS] = labels
        return result
