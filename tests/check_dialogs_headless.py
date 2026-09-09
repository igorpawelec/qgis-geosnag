"""Instantiate both algorithms under a headless QGIS and list their parameters with help texts.
    "C:/Program Files/QGIS 4.2.2/bin/python-qgis.bat" tests/check_dialogs_headless.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qgis.core import QgsApplication  # noqa: E402

app = QgsApplication([], False)
app.initQgis()
from geosnag_plugin.algorithms.detect import DetectDeadTreesAlgorithm  # noqa: E402
from geosnag_plugin.algorithms.grow import GrowCrownsAlgorithm  # noqa: E402

for cls in (DetectDeadTreesAlgorithm, GrowCrownsAlgorithm):
    alg = cls()
    alg.initAlgorithm()
    params = alg.parameterDefinitions()
    with_help = sum(1 for p in params if getattr(p, "help", lambda: "")())
    print(f"{alg.displayName()}: {len(params)} parameters, {with_help} with help; QGIS {app.applicationVersion() if hasattr(app, 'applicationVersion') else ''}")
    for p in params:
        adv = "advanced" if (p.flags() & p.FlagAdvanced) else "main"
        print(f"  [{adv}] {p.name():17s} {p.description()[:90]}")
    assert len(alg.shortHelpString()) > 500
print("KONIEC")
app.exitQgis()
