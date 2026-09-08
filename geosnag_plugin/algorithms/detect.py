"""Detect dead trees -- wraps pygeosnag.detect. One point per dead tree.

Five things on the dialog: the orthophoto, the band mode, the threshold,
an optional stand layer and the output. The rest sits under Advanced with
the values the research calibrated: since assets-v2 that includes the scene
normalisation the RGB+NIR and CIR models expect and an optional cut on the
object score.
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
from ._base import (MODE_KEYS, MODES, RADIOMETRY_KEYS, RADIOMETRY_OPTIONS, SCENE_NORM_KEYS, SCENE_NORM_OPTIONS,
                    advanced, package_error, progress_adapter, report_models, require_packages, set_assets_dir,
                    source_path, warm_jit)


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
    CHM = "CHM"
    DSM = "DSM"
    DTM = "DTM"
    MIN_HEIGHT = "MIN_HEIGHT"
    HEIGHT_RADIUS = "HEIGHT_RADIUS"
    KEEP_LOW = "KEEP_LOW"
    ASSETS = "ASSETS"
    PROB = "PROB"
    OBJECT_THRESHOLD = "OBJECT_THRESHOLD"
    SCENE_NORM = "SCENE_NORM"
    NORM_TILES = "NORM_TILES"
    RADIOMETRY = "RADIOMETRY"

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
            "random forest trained with whole-crown labels on ten Polish forest sites (the "
            "pygeosnag models <code>assets-v2</code>), a probability threshold, adjacent "
            "detections merged and their centroid taken as the point. The points are seeds for "
            "<i>Grow crowns</i>.</p>"
            "<p><b>Band mode.</b> Auto reads 4 bands as R, G, B, NIR (or NIR, R, G, B when the "
            "first band is the brightest) and 3 bands as CIR when the second band is the darkest "
            "over a sample of the pixels (vegetation absorbs red), else as RGB; the first log line "
            "says which. Choose the mode yourself when you know it: a CIR orthophoto read as RGB "
            "finds almost nothing.</p>"
            "<p><b>Threshold.</b> 0.7 is the models' operating point. On a scene never seen in "
            "training (Bialowieza, 2018 flight) recall stays at 61% from 0.6 to 0.8 while "
            "precision rises from 23% to 30%: lower it for completeness, raise it for a cleaner "
            "map. On imagery unlike the training sites (another camera, species or decay stage) "
            "the ranking is usually right and the scale is not: lower it.</p>"
            "<p><b>Scene normalisation.</b> The RGB+NIR and CIR models score spectral means "
            "standardised within the scene: a first pass over 16 tiles (Advanced) gathers the "
            "scene's medians and spreads before any tile is scored. This is what lets a model "
            "trained on one set of flights read a flight with a different colour balance. Leave "
            "it on auto; the models' manifest decides.</p>"
            "<p><b>Radiometry.</b> A rescue, off by default. With <i>auto</i> the per-band 2nd and "
            "98th percentiles of the sampled tiles are compared with those of the training "
            "orthophotos and a hazy or flat scene is mapped onto the training range before "
            "segmentation. On some scenes the models see nothing at all without it; on others it "
            "removes most detections (mapping the bands separately changes the band ratios). Run "
            "with it off first; switch to auto only on a scene that plainly holds dead trees and "
            "returned nothing. The log says what was measured.</p>"
            "<p><b>Object score.</b> RGB+NIR points also carry <code>p_object</code>, a second, "
            "stricter score from a forest that looks at the whole merged object. Dropping points "
            "below 0.4 (Advanced) keeps about two thirds of the trees at half the false points.</p>"
            "<p><b>Stand polygons.</b> Optional. Forest-management polygons with a stand age "
            "field (<code>species_age</code>): points inside stands of at least 10 years, "
            "shrunk by 2 m, are kept; roads and fields fall out.</p>"
            "<p><b>Canopy height model.</b> Optional, a ground separator and nothing more: a "
            "point with nothing taller than 3 m within 3 m of it (Advanced) is bare ground, a "
            "road or a shadow edge, not a standing tree, and is dropped. The maximum in a "
            "neighbourhood is used because an orthophoto and a height model rarely put the same "
            "crown in the same place; the model says nothing about the crown itself. A surface "
            "and a terrain model (GUGiK NMPT and NMT) can be given instead under Advanced; their "
            "difference is used. Mind the vintage: a height model taken after the imagery shows "
            "cleared stands where the dead trees stood. The height is written as "
            "<code>height_m</code>.</p>"
            "<p>Measured with the site under test never seen in training (a hit within 1.5 m of "
            "a reference top): F1 0.61 for RGB+NIR, 0.55 for CIR and for RGB. On Bialowieza, "
            "never trained on, 61% of the trees dead by the flight at the operating point, "
            "against an ALS reference that is not the image's.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto"))
        self.addParameter(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, "Probability threshold (0.7 = the models' operating point; lower for completeness or on an unfamiliar scene)",
            QgsProcessingParameterNumber.Double, defaultValue=0.7, minValue=0.05, maxValue=0.95))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.STANDS, "Stand polygons (optional mask)", [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.CHM, "Canopy height model (optional; drops points with nothing taller than 3 m within 3 m)", optional=True))
        self.addParameter(advanced(QgsProcessingParameterRasterLayer(
            self.DSM, "Surface model (DSM), with the terrain model an alternative to the CHM", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterRasterLayer(
            self.DTM, "Terrain model (DTM)", optional=True)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.MIN_HEIGHT, "Height gate (m): drop points with nothing taller than this nearby",
            QgsProcessingParameterNumber.Double, defaultValue=3.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.HEIGHT_RADIUS, "Height gate: radius of 'nearby' (m); the crown and the height model rarely line up exactly",
            QgsProcessingParameterNumber.Double, defaultValue=3.0, minValue=0.0)))
        self.addParameter(advanced(QgsProcessingParameterBoolean(
            self.KEEP_LOW, "Keep points below the gate, with height_m written", defaultValue=False)))
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
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.OBJECT_THRESHOLD, "Drop RGB+NIR points with p_object below (0 = keep all; 0.4 halves the false points)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0, maxValue=1.0)))
        self.addParameter(advanced(QgsProcessingParameterEnum(
            self.SCENE_NORM, "Scene normalisation of the spectral means", options=SCENE_NORM_OPTIONS, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterNumber(
            self.NORM_TILES, "Scene normalisation: tiles sampled for the scene statistics",
            QgsProcessingParameterNumber.Integer, defaultValue=16, minValue=1)))
        self.addParameter(advanced(QgsProcessingParameterEnum(
            self.RADIOMETRY, "Radiometry (rescue for a scene that returned nothing; off first)",
            options=RADIOMETRY_OPTIONS, defaultValue=0)))
        self.addParameter(advanced(QgsProcessingParameterFile(
            self.ASSETS, "Local models folder (remembered; empty = last used or download)",
            behavior=QgsProcessingParameterFile.Folder, optional=True)))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Dead trees", type=QgsProcessing.TypeVectorPoint))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.PROB, "Probability raster", optional=True, createByDefault=False))

    def prepareAlgorithm(self, parameters, context, feedback):
        warm_jit(feedback)
        styling.register_output_styles(feedback)     # QGIS styles the outputs itself (Postprocessing.py)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        require_packages(feedback)
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        mode = MODE_KEYS[self.parameterAsEnum(parameters, self.MODE, context)]
        bands_s = (self.parameterAsString(parameters, self.BANDS, context) or "").strip()
        bands = tuple(b.strip() for b in bands_s.split(",")) if bands_s else None
        stands_layer = self.parameterAsVectorLayer(parameters, self.STANDS, context)
        stands, stand_layer = _split_source(stands_layer) if stands_layer is not None else (None, None)
        chm_layer = self.parameterAsRasterLayer(parameters, self.CHM, context)
        dsm_layer = self.parameterAsRasterLayer(parameters, self.DSM, context)
        dtm_layer = self.parameterAsRasterLayer(parameters, self.DTM, context)
        chm = source_path(chm_layer) if chm_layer is not None else None
        dsm = source_path(dsm_layer) if dsm_layer is not None else None
        dtm = source_path(dtm_layer) if dtm_layer is not None else None
        if (dsm is None) != (dtm is None):
            raise QgsProcessingException("Give both the surface and the terrain model, or a canopy height model.")
        set_assets_dir(self.parameterAsFile(parameters, self.ASSETS, context) or None, feedback)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        if not out.lower().endswith(".gpkg"):
            raise QgsProcessingException("The output must be a GeoPackage (.gpkg): pygeosnag writes it directly.")
        prob = self.parameterAsOutputLayer(parameters, self.PROB, context) or None
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)
        object_threshold = self.parameterAsDouble(parameters, self.OBJECT_THRESHOLD, context) or None
        scene_norm = SCENE_NORM_KEYS[self.parameterAsEnum(parameters, self.SCENE_NORM, context)]
        norm_tiles = self.parameterAsInt(parameters, self.NORM_TILES, context)
        radiometry = RADIOMETRY_KEYS[self.parameterAsEnum(parameters, self.RADIOMETRY, context)]
        report_models(feedback, threshold)
        from pygeosnag.detect import detect
        try:
            n = detect(source_path(layer), out, mode=mode, bands=bands,
                       threshold=threshold, object_threshold=object_threshold,
                       scene_norm=scene_norm, norm_tiles=norm_tiles, radiometry=radiometry,
                       suppress_m=self.parameterAsDouble(parameters, self.SUPPRESS, context),
                       stands=stands, stand_layer=stand_layer,
                       stand_age=self.parameterAsDouble(parameters, self.STAND_AGE, context),
                       stand_buffer=self.parameterAsDouble(parameters, self.STAND_BUFFER, context),
                       keep_outside=self.parameterAsBool(parameters, self.KEEP_OUTSIDE, context),
                       chm=chm, dsm=dsm, dtm=dtm,
                       min_height=self.parameterAsDouble(parameters, self.MIN_HEIGHT, context),
                       height_radius=self.parameterAsDouble(parameters, self.HEIGHT_RADIUS, context),
                       keep_low=self.parameterAsBool(parameters, self.KEEP_LOW, context),
                       prob_raster=prob, progress=progress_adapter(feedback), quiet=True)
        except RuntimeError as e:
            if "cancelled" in str(e):
                return {}
            raise package_error(e)
        except (ValueError, OSError) as e:
            raise package_error(e)
        except TypeError as e:
            if "scene_norm" in str(e) or "object_threshold" in str(e) or "radiometry" in str(e):
                raise QgsProcessingException(
                    "An older pygeosnag (< 0.3.2) is installed in QGIS's Python and shadows the copy bundled "
                    "with the plugin. Uninstall it or upgrade it; the bundled copy is then used.") from e
            raise
        feedback.pushInfo(f"{n} dead trees")
        styling.style_points(context, out)
        if prob:
            styling.style_stretched_raster(context, prob)
        result = {self.OUTPUT: out}
        if prob:
            result[self.PROB] = prob
        return result
