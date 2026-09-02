"""Plugin entry: register the Processing provider, put the bundled packages
on the path.

The provider is always registered so the toolbox entry appears; whether the
wrapped packages are importable is a per-run concern handled in each
algorithm (they call deps.ensure_dependencies and report to the Processing
log rather than crashing the plugin at load).
"""
from qgis.core import QgsApplication

from .provider import GeoSnagProvider


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        try:
            from . import vendor_loader
            # A reinstalled zip must not keep running the previous zip's
            # package code that is still in sys.modules.
            vendor_loader.purge_stale()
            vendor_loader.activate()
        except Exception:
            pass
        self.provider = GeoSnagProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
