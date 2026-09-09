"""Grow crowns -- wraps pygeosnag.grow_crowns: each dead-tree point grows into
its crown polygon (seeded region growing with the crown recipe)."""
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
from ._base import progress_adapter, MODE_KEYS, MODES, advanced, hp, package_error, require_packages, source_path, warm_jit

SPACES = ["auto: NDVI + lightness when the raster has an infrared band, CIELAB colour when it has not",
          "ndvi_L: NDVI and lightness (needs the infrared band)",
          "lab_w: CIELAB colour with the red-green axis weighted (the RGB recipe)",
          "lab: CIELAB colour, all axes equal",
          "raw: the band values as they are"]
SPACE_KEYS = ["auto", "ndvi_L", "lab_w", "lab", "raw"]
RULES = ["auto: the rule each feature space was tuned with (recommended)",
         "reach: a pixel goes to the nearest-looking point within the radius",
         "partition: one global partition of the image between all points, then cut by tolerance and radius"]
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
            "<p><b>Each dead-tree point grows into its crown polygon.</b> Starting at the pixel "
            "under the point, the crown takes in the neighbouring pixels that still look like that "
            "pixel, up to a spectral tolerance and a maximum radius, while neighbouring points "
            "compete for the pixels between them (seeded region growing). Holes inside a crown are "
            "filled. The points can come from <i>Detect dead trees</i>, from a click or from a "
            "field survey, as long as they sit on the crown.</p>"
            "<p><b>What 'looks alike' means.</b> With an infrared band the crown grows on NDVI and "
            "lightness: a dead crown has lost its infrared reflectance and is usually brighter than "
            "the canopy, so both separate it from the living neighbours and from shadow. Without "
            "infrared it grows on CIELAB colour with the red-green axis weighted, which is what "
            "separates a grey-white crown from green canopy in plain RGB.</p>"
            "<p><b>What you get.</b> A polygon layer <i>Crowns</i>, one (multi)polygon per point, "
            "with <code>adaptel_id</code> (the index of the point), <code>area_m2</code>, "
            "<code>perimeter</code> and <code>n_parts</code>. Optionally a label raster with the "
            "point index in every crown pixel.</p>"
            "<p><b>How good is it.</b> On 1 200 verified crowns of eight Polish sites, with the "
            "detector's own points as neighbours, the grown crowns overlap the verified ones with a "
            "median IoU of 0.70 (eight in ten above 0.5) on infrared imagery and 0.52 on RGB; the "
            "crowns tend to be a little smaller than the verified outlines, because thin, shaded "
            "branches at the edge fall outside the tolerance.</p>"
            "<p><b>Advanced.</b> The feature space and the assignment rule, the tolerance at the "
            "seed and at the radius, the radius, the band weights and hole filling. The defaults are "
            "the values the recipe was tuned with; 0 or an empty field means 'use them'. Every "
            "option explains itself in its help text.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(hp(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto (the one the points were detected on)"),
                             "The same orthophoto the points come from. Any band order the band mode understands."))
        self.addParameter(hp(QgsProcessingParameterVectorLayer(
            self.POINTS, "Dead trees (points)", [QgsProcessing.TypeVectorPoint]),
            "One point per tree, on the crown. From Detect dead trees, a click or a field survey."))
        self.addParameter(advanced(hp(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0),
                                      "Which band holds what; auto reads it from the pixels and writes its choice in the log. "
                                      "It decides whether the crown can grow on NDVI (needs the infrared band).")))
        self.addParameter(advanced(hp(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order, e.g. nir,red,green,blue (overrides the band mode)", defaultValue="", optional=True),
            "For an unusual band order: comma-separated roles (red, green, blue, nir) in the order of the bands.")))
        self.addParameter(advanced(hp(QgsProcessingParameterEnum(self.SPACE, "Feature space: what 'looks alike' means", options=SPACES, defaultValue=0),
                                      "The values a pixel is compared on. auto picks NDVI + lightness with an infrared band and "
                                      "weighted CIELAB colour without; the tolerances below are per space, so change the space "
                                      "first and the tolerance after.")))
        self.addParameter(advanced(hp(QgsProcessingParameterEnum(self.RULE, "Assignment rule: how neighbouring points share pixels", options=RULES, defaultValue=0),
                                      "reach: every pixel within the radius and tolerance of a point goes to the point it looks "
                                      "most like along the way; fuller crowns in dense clusters. partition: the whole image is "
                                      "split between all points first and cut afterwards; cannot grow into shadow between "
                                      "points, better on RGB. auto pairs each feature space with the rule it was tuned with.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.MAX_COST, "Tolerance at the seed (0 = the space's own)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0),
            "How different from the seed pixel a pixel may be and still join the crown. Larger = fuller "
            "crowns that may spill into shadow or ground; smaller = tighter crowns with holes at the edges. "
            "Per space: NDVI + lightness 28 (units of 100 x NDVI and L), CIELAB 15 (colour difference).")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.MAX_COST_R, "Tolerance at the radius (0 = the space's own; NDVI + lightness 12)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0),
            "The tolerance falls from the seed value to this at the maximum radius, so a crown is generous "
            "near its point and strict at its edge. Lowering it stops the spill into shadow at the edges; "
            "raising it grows fuller edges. For CIELAB the tolerance is flat (this equals the seed value).")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.MAX_RADIUS, "Maximum crown radius (px): 20 = 5 m at 0.25 m", QgsProcessingParameterNumber.Integer,
            defaultValue=20, minValue=2),
            "No crown reaches farther than this from its point. Raise it for large old crowns or a finer "
            "pixel, lower it for young stands or a coarser pixel.")))
        self.addParameter(advanced(hp(QgsProcessingParameterString(
            self.WEIGHTS, "Band weights, one per feature (empty = the space's own)", defaultValue="", optional=True),
            "How much each feature counts in the difference: for CIELAB three numbers (L, a, b; the recipe "
            "is 0.5, 2.5, 1.0), for NDVI + lightness two (1, 1).")))
        self.addParameter(advanced(hp(QgsProcessingParameterBoolean(
            self.FILL_HOLES, "Fill holes inside crowns", defaultValue=True),
            "Checked: pixels enclosed by a crown (a shaded branch, a bright spot) are added to it. Unchecked: "
            "crowns keep their holes.")))
        self.addParameter(hp(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Crowns", type=QgsProcessing.TypeVectorPolygon),
            "The crowns, one (multi)polygon per point, as a GeoPackage (.gpkg)."))
        self.addParameter(hp(QgsProcessingParameterRasterDestination(
            self.LABELS, "Label raster (optional)", optional=True, createByDefault=False),
            "A raster with the point index in every crown pixel and -1 elsewhere, for raster-based follow-ups."))

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
                    "(e.g. 0.5,2.5,1.0 for CIELAB, 1,1 for NDVI + lightness), or empty for the space's own weights")
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
