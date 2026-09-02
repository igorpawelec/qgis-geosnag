"""The Processing provider: Detect dead trees (points) and Grow crowns."""
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.detect import DetectDeadTreesAlgorithm
from .algorithms.grow import GrowCrownsAlgorithm


class GeoSnagProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        for alg in (DetectDeadTreesAlgorithm(), GrowCrownsAlgorithm()):
            self.addAlgorithm(alg)

    def id(self):
        return "geosnag"

    def name(self):
        # Identical to `name=` in metadata.txt on purpose: the Plugin Manager
        # reads that one and the toolbox reads this one.
        return "GeoSnag"

    def longName(self):
        return "GeoSnag (standing dead trees on orthophotos: points, then crowns)"

    def icon(self):
        p = os.path.join(os.path.dirname(__file__), "icon.png")
        return QIcon(p) if os.path.exists(p) else QgsProcessingProvider.icon(self)
