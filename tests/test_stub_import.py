"""Import the plugin and build its dialogs against a stub `qgis` module.

What can be checked without a QGIS: every module imports, the provider
lists its algorithms, every algorithm builds its parameters, the styling
entry points exist, and the dependency bootstrap computes its pip specs.
The stub (tests/qgis_stub) makes every qgis.core name a permissive dummy,
so a wrong parameter class name or a missing import is caught here and
not in the operator's QGIS.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _setup():
    for p in (os.path.join(HERE, "qgis_stub"), ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)


def test_provider_lists_two_algorithms():
    _setup()
    from geosnag_plugin.provider import GeoSnagProvider
    prov = GeoSnagProvider()
    prov.loadAlgorithms()
    assert prov.id() == "geosnag" and prov.name() == "GeoSnag"


def test_algorithms_build_their_parameters():
    _setup()
    from geosnag_plugin.algorithms.detect import DetectDeadTreesAlgorithm
    from geosnag_plugin.algorithms.grow import GrowCrownsAlgorithm
    for cls, name in ((DetectDeadTreesAlgorithm, "detect"), (GrowCrownsAlgorithm, "grow")):
        a = cls()
        a.initAlgorithm()
        assert a.name() == name and a.group() == "Dead trees"
        assert len(a.shortHelpString()) > 200
        assert a.createInstance().name() == name


def test_styling_and_deps_helpers():
    _setup()
    from geosnag_plugin import deps, styling, vendor_loader
    assert callable(styling.style_points) and callable(styling.style_polygons)
    assert callable(styling.style_stretched_raster)
    specs = deps._install_specs()
    assert "scikit-learn" in specs and "numba" in specs
    assert vendor_loader.LIBS_DIR.endswith("libs")
    assert vendor_loader.purge_stale() == 0
