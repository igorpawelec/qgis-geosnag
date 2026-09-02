"""The Processing provider: two algorithms."""
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.adapt import AdaptModelAlgorithm
from .algorithms.detect import DetectDeadTreesAlgorithm


class GeoSnagProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        for alg in (DetectDeadTreesAlgorithm(), AdaptModelAlgorithm()):
            self.addAlgorithm(alg)

    def id(self):
        return "geosnag"

    def name(self):
        # Identical to `name=` in metadata.txt on purpose: the Plugin Manager
        # reads that one and the toolbox reads this one.
        return "GeoSnag"

    def longName(self):
        return "GeoSnag (standing dead tree detection on orthophotos)"

    def icon(self):
        p = os.path.join(os.path.dirname(__file__), "icon.png")
        return QIcon(p) if os.path.exists(p) else QgsProcessingProvider.icon(self)
