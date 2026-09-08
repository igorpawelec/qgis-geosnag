"""Grow crowns -- wraps pygeosnag.grow_crowns (seeded region growing with the
crown recipe: since pygeosnag 0.4.0 the within-reach kernel on NDVI + L)."""
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
from ._base import progress_adapter, MODE_KEYS, MODES, advanced, package_error, require_packages, source_path, warm_jit

SPACES = ["auto (NDVI + lightness with a NIR band, else weighted CIELAB)",
          "ndvi_L (100 x NDVI and CIELAB L; needs a NIR band; tolerance 28 at the seed, 12 at the radius)",
          "lab_w (CIELAB with a* weighted 2.5, the recipe before 0.4.9; tolerance 15)",
          "lab (CIELAB, equal weights; tolerance 20)",
          "raw (the bands as they are; tolerance 35, not benchmarked)"]
SPACE_KEYS = ["auto", "ndvi_L", "lab_w", "lab", "raw"]
RULES = ["auto (reach on NDVI + lightness, partition on CIELAB and raw: the pairing each was benchmarked in)",
         "reach (a pixel goes to the seed within the radius and tolerance with the lowest path cost)",
         "partition (one global partition with every seed, cut afterwards; the behaviour before 0.4.9)"]
RULE_KEYS = ["auto", "reach", "partition"]


class GrowCrownsAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    POINTS = "POINTS"
    OUTPUT = "OUTPUT"
    # advanced
    MODE = "MODE"
    BANDS = "BANDS"
    SPACE = "SPACE"
    RULE = "RULE"
    MAX_COST = "MAX_COST"
    MAX_COST_R = "MAX_COST_R"
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
            "pixels within a radius that stay within a spectral tolerance of the pixel it sits "
            "on, competing with the other points (pygeosnag's within-reach seeded region "
            "growing, inverse OBIA).</p>"
            "<p>The default recipe (pygeosnag 0.4.1) grows on 100 x NDVI and CIELAB lightness "
            "with a tolerance of 28 at the seed falling to 12 at the radius, at most 20 px "
            "(5 m at 0.25 m) from the seed, holes inside a crown filled; a raster without a "
            "NIR band falls back to CIELAB with a* weighted 2.5, a flat tolerance of 15 and the "
            "global partition rule, i.e. exactly the recipe before 0.4.9. Benchmarked on 1200 verified crowns of 8 Polish sites with "
            "the detector's own points as competitors: median IoU 0.70, 79% of the crowns above "
            "0.5, against 0.53 and 54% for the previous recipe; on dense bark-beetle clusters "
            "(Gizycko, 2000 crowns) 0.56 against 0.34. Points can also come from anywhere else "
            "&mdash; a click, a field survey &mdash; as long as they sit on the crown.</p>"
            "<p>Under Advanced: the feature space and the assignment rule; a tolerance of 0 and "
            "empty weights mean the values the chosen space was benchmarked at. For very dense "
            "clusters a higher tolerance at the seed (32) grows fuller crowns at the price of "
            "some spill in sparse stands.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.POINTS, "Dead trees (points)", [QgsProcessing.TypeVectorPoint]))
        self.addParameter(advanced(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order (empty = default order)", defaultValue="", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterEnum(self.SPACE, "Feature space", options=SPACES, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterEnum(self.RULE, "Assignment rule", options=RULES, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MAX_COST, "Spectral tolerance at the seed (0 = the value of the chosen space)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MAX_COST_R, "Spectral tolerance at the radius (0 = the seed tolerance minus the taper of the space; ndvi_L 12)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MAX_RADIUS, "Maximum radius from the seed (px)", QgsProcessingParameterNumber.Integer,
            defaultValue=20, minValue=2)))
        self.addParameter(advanced(QgsProcessingParameterString(
            self.WEIGHTS, "Band weights, one per feature (empty = the weights of the chosen space)",
            defaultValue="", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.FILL_HOLES, "Fill holes inside crowns", defaultValue=True)))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Crowns", type=QgsProcessing.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.LABELS, "Label raster", optional=True, createByDefault=False))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        styling.register_output_styles(feedback)     # QGIS styles the outputs itself (Postprocessing.py)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        pts = self.parameterAsVectorLayer(parameters, self.POINTS, context)
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        space = SPACE_KEYS[self.parameterAsEnum(parameters, self.SPACE, context)]
        rule = RULE_KEYS[self.parameterAsEnum(parameters, self.RULE, context)]
        max_cost = self.parameterAsDouble(parameters, self.MAX_COST, context)
        max_cost = max_cost if max_cost > 0 else None          # None = the space's own tolerance
        cost_r = self.parameterAsDouble(parameters, self.MAX_COST_R, context)
        taper = None                                           # None = the space's own taper
        if cost_r > 0:
            seed_cost = max_cost
            if seed_cost is None:
                try:
                    from pygeosnag.grow import SPACES_REACH
                    seed_cost = SPACES_REACH.get(space, {}).get("max_cost")
                except ImportError:
                    seed_cost = None
            if seed_cost is None:
                raise QgsProcessingException(
                    "Set the tolerance at the seed as well: with feature space auto the seed tolerance is only "
                    "known once the raster is read.")
            taper = max(0.0, float(seed_cost) - cost_r)
        weights_s = (self.parameterAsString(parameters, self.WEIGHTS, context) or "").strip()
        weights = None
        if weights_s:
            try:
                weights = tuple(float(x) for x in weights_s.split(","))
            except ValueError:
                raise QgsProcessingException(
                    "Band weights must be numbers separated by commas, one per feature "
                    "(e.g. 0.5,2.5,1.0 for CIELAB, 1,1 for NDVI + L), or empty for the space's own weights")
        radius = self.parameterAsInt(parameters, self.MAX_RADIUS, context)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if not out.lower().endswith(".gpkg"):
            raise QgsProcessingException("The output must be a GeoPackage (.gpkg): pygeosnag writes it directly.")
        labels = self.parameterAsOutputLayer(parameters, self.LABELS, context) or None
        from pygeosnag.grow import grow_crowns
        feedback.pushInfo(f"Growing the points tile by tile: feature space {space}, rule {rule}, tolerance "
                          f"{'of the space' if max_cost is None else max_cost}"
                          f"{'' if taper is None else f' at the seed, {cost_r:g} at the radius'}, radius {radius} px.")
        try:
            n = grow_crowns(source_path(layer), pts.source(), out, mode=mode, bands=bands, labels_out=labels,
                            space=space, rule=rule, max_cost=max_cost, taper=taper, band_weights=weights,
                            max_radius=radius, fill_holes=self.parameterAsBool(parameters, self.FILL_HOLES, context),
                            progress=progress_adapter(feedback), quiet=True)
        except RuntimeError as e:
            if "cancelled" in str(e):
                return {}
            raise package_error(e)
        except (ValueError, OSError) as e:
            raise package_error(e)
        except TypeError as e:
            if any(k in str(e) for k in ("progress", "tile", "space", "rule", "taper")):
                raise QgsProcessingException(
                    "An older pygeosnag (< 0.4.1) shadows the copy bundled with the plugin; see the Running: line.") from e
            raise
        feedback.pushInfo(f"{n} crowns")
        styling.style_polygons(context, out)
        result = {self.OUTPUT: out}
        if labels:
            result[self.LABELS] = labels
        return result
