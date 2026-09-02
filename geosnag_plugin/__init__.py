"""GeoSnag -- a QGIS Processing provider for pygeosnag.

Standing dead tree detection on aerial orthophotos. The algorithms live in
the pygeosnag package; this plugin is glue. Copyright (C) 2026 Igor Pawelec.
GPLv3.
"""


def classFactory(iface):
    from .plugin import Plugin
    return Plugin(iface)
