"""Detect dead trees -- wraps pygeosnag.detect. One point per standing dead tree.

The dialog shows what most users need: the orthophoto, the band mode, the
threshold, optional stand polygons and a canopy height model, the output.
Everything else sits under Advanced with the values the models were
calibrated with.
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
                    advanced, hp, package_error, progress_adapter, report_models, require_packages, set_assets_dir,
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
            "<p><b>One point per standing dead tree, from the orthophoto alone.</b> The image is "
            "split into adaptels (small segments that follow the crowns), each segment is described "
            "by its colour, its contrast to the surroundings and its texture, and a random forest "
            "trained on verified dead trees scores it. Segments above the threshold are merged "
            "into objects; each object becomes one point with a confidence <code>p</code>. No tree "
            "tops, no height model and no training are needed.</p>"
            "<p><b>What you get.</b> A point layer <i>Dead trees</i> with <code>p</code> (confidence "
            "of the best segment), <code>p_mean</code>, <code>p_object</code> (RGB+NIR only, see "
            "below), <code>area_m2</code> (the object), <code>n_adaptels</code>, "
            "<code>height_m</code> and <code>in_stands</code> when a height model or stands were "
            "given, and <code>edge_px</code> (distance to the raster edge). The points are the "
            "seeds for <i>Grow crowns</i>.</p>"
            "<p><b>Orthophoto.</b> Leaf-on aerial imagery at about 0.25 m works best; 0.10 to "
            "0.50 m works. RGB+NIR is best, colour infrared (CIR) nearly as good, plain RGB "
            "clearly weaker (a bleached crown looks like bare ground without the infrared band).</p>"
            "<p><b>Band mode.</b> <i>auto</i> reads the band order from the pixels and writes its "
            "decision in the first log line. Set it yourself when you know it: a CIR orthophoto "
            "read as RGB finds almost nothing.</p>"
            "<p><b>Threshold.</b> 0 uses the value each model was calibrated with (0.7; 0.6 for "
            "RGB). Lower it to find more trees at the price of more false points; raise it for a "
            "cleaner but thinner map. On imagery unlike the training data (another camera, "
            "region or decay stage) the ranking of the points is usually right and the scale is "
            "not, so start lower.</p>"
            "<p><b>Stand polygons.</b> Optional. Forest-management polygons with a stand age "
            "field (<code>species_age</code>): only points inside stands at least 10 years old, "
            "shrunk by 2 m, are kept, which removes roads, fields and stand edges.</p>"
            "<p><b>Canopy height model.</b> Optional. A point with nothing taller than 3 m within "
            "3 m of it is bare ground, a road or a shadow edge, not a standing tree, and is "
            "dropped. Only the maximum height nearby is used, because an orthophoto and a height "
            "model rarely put the same crown in the same place. Mind the vintage: a model taken "
            "after the imagery shows cleared stands where the dead trees stood.</p>"
            "<p><b>Advanced.</b> The height gate, the stand mask and the merging distance; the "
            "object score <code>p_object</code> (RGB+NIR only: a second forest looks at the whole "
            "object; dropping points below 0.4 removes about half of the false points and a third "
            "of the trees); scene normalisation (leave on auto); the radiometry rescue for an "
            "orthophoto so hazy or flat that nothing is found (off first, then auto); a local "
            "models folder for offline use; a probability raster. Every option explains itself "
            "in its help text.</p>"
            "<p><b>How good is it.</b> With the test site never used for training, roughly six in "
            "ten verified dead trees are found at the default threshold with about the same share "
            "of the points being true trees (F1 about 0.6) on RGB+NIR and CIR imagery of Polish "
            "lowland pine and spruce stands; RGB is weaker. The models were trained on sites "
            "surveyed for the author's publication and by the State Forests' task force on dead "
            "tree monitoring.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(hp(QgsProcessingParameterRasterLayer(self.INPUT, "Orthophoto (RGB+NIR, CIR or RGB; best at about 0.25 m)"),
                             "Leaf-on aerial orthophoto. Four bands are read as RGB+NIR, three as colour infrared or RGB "
                             "(see Band mode). Any pixel size from 0.10 to 0.50 m works; the models were trained at 0.25 m."))
        self.addParameter(hp(QgsProcessingParameterEnum(self.MODE, "Band mode", options=MODES, defaultValue=0),
                             "Which band holds what. auto samples the pixels and decides (4 bands: RGB+NIR, or NIR first when "
                             "the first band is the brightest; 3 bands: CIR when the second band is the darkest, because "
                             "vegetation absorbs red, else RGB) and writes its choice in the first log line. Set it "
                             "yourself when you know the order: a CIR image read as RGB finds almost nothing."))
        self.addParameter(hp(QgsProcessingParameterNumber(
            self.THRESHOLD, "Probability threshold (0 = the model's own: 0.7, RGB 0.6)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0, maxValue=0.95),
            "A segment is a dead-tree candidate when its confidence reaches this value. Lower = more trees "
            "found and more false points; higher = fewer, cleaner points. 0 takes the value the model of the "
            "band mode was calibrated with. On unfamiliar imagery start lower (0.5) and look at the map."))
        self.addParameter(hp(QgsProcessingParameterVectorLayer(
            self.STANDS, "Stand polygons: keep only points inside forest stands (optional)", [QgsProcessing.TypeVectorPolygon], optional=True),
            "Forest-management polygons. Points outside stands, in stands younger than the minimum age (Advanced) "
            "or within the buffer of a stand edge are dropped: roads, fields and clear-cuts fall out. A field "
            "named species_age holds the stand age; without it every polygon counts as a stand."))
        self.addParameter(hp(QgsProcessingParameterRasterLayer(
            self.CHM, "Canopy height model: drop points with nothing taller than 3 m nearby (optional)", optional=True),
            "A canopy height model (or a surface and a terrain model under Advanced). A point with no pixel "
            "above the height gate within the gate radius stands on the ground and is dropped. The height "
            "found is written as height_m. Use a model from the same years as the imagery: a later one shows "
            "cleared stands where the dead trees stood, an earlier one is mostly harmless."))
        self.addParameter(advanced(hp(QgsProcessingParameterRasterLayer(
            self.DSM, "Surface model (DSM), with the terrain model an alternative to the CHM", optional=True),
            "Digital surface model. Together with the terrain model it replaces the canopy height model: the "
            "gate uses their difference.")))
        self.addParameter(advanced(hp(QgsProcessingParameterRasterLayer(self.DTM, "Terrain model (DTM)", optional=True),
                                      "Digital terrain model, used only together with the surface model.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.MIN_HEIGHT, "Height gate (m): a point needs something at least this tall nearby",
            QgsProcessingParameterNumber.Double, defaultValue=3.0, minValue=0.0),
            "Points whose neighbourhood holds nothing taller than this are dropped. 3 m separates ground, "
            "roads and shadow edges from trees; raise it in tall stands with a lot of understorey, lower it "
            "for young stands.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.HEIGHT_RADIUS, "Height gate radius (m): how far to look for that height",
            QgsProcessingParameterNumber.Double, defaultValue=3.0, minValue=0.0),
            "The maximum height within this distance of the point is compared with the gate. 3 m absorbs the "
            "usual offset between an orthophoto and a height model; a smaller radius drops more true trees "
            "whose crown sits a little off in the height model.")))
        self.addParameter(advanced(hp(QgsProcessingParameterBoolean(
            self.KEEP_LOW, "Keep the points below the height gate, only flagged", defaultValue=False),
            "Checked: nothing is dropped by the height gate; every point gets height_m and you filter later. "
            "Unchecked: points below the gate are removed from the output.")))
        self.addParameter(advanced(hp(QgsProcessingParameterString(
            self.BANDS, "Band roles in raster order, e.g. nir,red,green,blue (overrides the band mode)",
            defaultValue="", optional=True),
            "For a raster with an unusual band order. Comma-separated roles in the order of the bands: red, "
            "green, blue, nir. Empty = the order the band mode implies.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.STAND_AGE, "Stands: minimum stand age (years) to keep points", QgsProcessingParameterNumber.Double,
            defaultValue=10.0, minValue=0.0),
            "Points in stands younger than this are dropped (young plantations hold no standing dead trees "
            "worth mapping and plenty of bare soil that looks like one). 0 keeps every stand.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.STAND_BUFFER, "Stands: buffer (m); negative shrinks the stands", QgsProcessingParameterNumber.Double,
            defaultValue=-2.0),
            "The stand polygons are buffered by this before the test. -2 m removes a 2 m band along every "
            "stand edge, where roads and shadows sit; 0 uses the polygons as they are; a positive value "
            "widens them.")))
        self.addParameter(advanced(hp(QgsProcessingParameterBoolean(
            self.KEEP_OUTSIDE, "Stands: keep the points outside too, flagged in_stands = 0", defaultValue=False),
            "Checked: nothing is dropped by the stand mask; every point gets in_stands (1 inside, 0 outside). "
            "Unchecked: points outside are removed.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.SUPPRESS, "Merge points closer than (m): the weaker of two is dropped", QgsProcessingParameterNumber.Double,
            defaultValue=3.0, minValue=0.0),
            "Two points closer than this are taken as one tree and the one with the lower confidence is "
            "dropped. 3 m suits crowns of 3 to 6 m; lower it for dense young stands, raise it for large "
            "old crowns that split into several objects. 0 keeps every object.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.OBJECT_THRESHOLD, "RGB+NIR only: drop points with p_object below (0 = keep all)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0, maxValue=1.0),
            "A second forest scores each merged object as a whole (its size, shape, contrast to the ring "
            "around it) into p_object. 0 keeps everything, p_object is only written. 0.4 removes about half "
            "of the false points and a third of the true trees. Only the RGB+NIR model has this second "
            "forest; for CIR and RGB the column stays empty and the cut does nothing.")))
        self.addParameter(advanced(hp(QgsProcessingParameterEnum(
            self.SCENE_NORM, "Scene normalisation of the spectral values", options=SCENE_NORM_OPTIONS, defaultValue=0),
            "The RGB+NIR and CIR models score colours standardised within the scene (a first pass over a "
            "sample of tiles measures the scene's typical values), which is what lets them read a flight "
            "with a different colour balance than the training flights. auto does what the model was "
            "trained with; off feeds raw values and is only right for a model trained that way.")))
        self.addParameter(advanced(hp(QgsProcessingParameterNumber(
            self.NORM_TILES, "Scene normalisation: tiles sampled for the scene statistics",
            QgsProcessingParameterNumber.Integer, defaultValue=16, minValue=1),
            "How many tiles the first pass reads to measure the scene. More = steadier statistics on a "
            "patchy scene and a slower start; 16 is enough for one flight.")))
        self.addParameter(advanced(hp(QgsProcessingParameterEnum(
            self.RADIOMETRY, "Radiometry rescue for an orthophoto that returned nothing",
            options=RADIOMETRY_OPTIONS, defaultValue=0),
            "For a hazy, dark or washed-out orthophoto on which the model finds nothing at all. auto "
            "compares the scene's brightness range with the training range and stretches the scene onto "
            "it only when it is clearly off; match always does. It helps on some scenes and hurts on others "
            "(stretching the bands separately shifts the colour ratios the model relies on), so run with "
            "off first and use it only on a scene that plainly holds dead trees and returned none. The log "
            "says what was measured.")))
        self.addParameter(advanced(hp(QgsProcessingParameterFile(
            self.ASSETS, "Local models folder (empty = the last used, or download)",
            behavior=QgsProcessingParameterFile.Folder, optional=True),
            "A folder holding manifest.json and the model files, for a machine without internet or a "
            "custom model set. Remembered between runs. Empty: the models are downloaded once into the "
            "user's cache.")))
        self.addParameter(hp(QgsProcessingParameterVectorDestination(
            self.OUTPUT, "Dead trees", type=QgsProcessing.TypeVectorPoint),
            "The points, one per dead tree, as a GeoPackage (.gpkg)."))
        self.addParameter(hp(QgsProcessingParameterRasterDestination(
            self.PROB, "Probability raster (optional)", optional=True, createByDefault=False),
            "Every pixel's confidence, for a look at what the model sees. Slower and large on a big orthophoto."))

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
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context) or None   # None = the mode's operating point
        object_threshold = self.parameterAsDouble(parameters, self.OBJECT_THRESHOLD, context) or None
        scene_norm = SCENE_NORM_KEYS[self.parameterAsEnum(parameters, self.SCENE_NORM, context)]
        norm_tiles = self.parameterAsInt(parameters, self.NORM_TILES, context)
        radiometry = RADIOMETRY_KEYS[self.parameterAsEnum(parameters, self.RADIOMETRY, context)]
        report_models(feedback, threshold, mode)
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
