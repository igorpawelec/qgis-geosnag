<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis styleCategories="Symbology" version="3.28">
  <!-- Adaptel probability 0-1 (nodata -1): fixed pseudocolour, no statistics
       read (a cumulative cut scanned every pixel on the GUI thread and crashed
       QGIS on a full orthophoto). Applied by Processing itself. -->
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" alphaBand="-1" classificationMin="0" classificationMax="1" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0" minimumValue="0" maximumValue="1" classificationMode="1" labelPrecision="2">
          <item value="0" color="#000000" alpha="0" label="0"/>
          <item value="0.3" color="#ffff96" alpha="90" label="0.3"/>
          <item value="0.5" color="#ffc800" alpha="170" label="0.5"/>
          <item value="0.7" color="#ff7800" alpha="210" label="0.7"/>
          <item value="1" color="#dc0000" alpha="240" label="1"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
