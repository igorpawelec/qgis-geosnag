<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis styleCategories="Symbology" version="3.28">
  <!-- Dead-tree points: four fixed classes of p around the assets-v2 operating
       point (0.7), hollow circles so the crown underneath stays visible.
       Applied by Processing itself (RenderingStyles), never by plugin code in
       the task-completion handler. -->
  <renderer-v2 type="graduatedSymbol" attr="p" graduatedMethod="GraduatedColor" symbollevels="0" forceraster="0" enableorderby="0">
    <ranges>
      <range lower="0" upper="0.6" symbol="0" label="&lt; 0.6" render="true"/>
      <range lower="0.6" upper="0.75" symbol="1" label="0.6 - 0.75" render="true"/>
      <range lower="0.75" upper="0.9" symbol="2" label="0.75 - 0.9" render="true"/>
      <range lower="0.9" upper="1.0001" symbol="3" label="&gt;= 0.9" render="true"/>
    </ranges>
    <symbols>
      <symbol type="marker" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <prop k="name" v="circle"/>
          <prop k="color" v="0,0,0,0"/>
          <prop k="outline_color" v="255,255,150,160"/>
          <prop k="outline_width" v="0.5"/>
          <prop k="outline_style" v="solid"/>
          <prop k="size" v="2.8"/>
          <prop k="size_unit" v="MM"/>
        </layer>
      </symbol>
      <symbol type="marker" name="1" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <prop k="name" v="circle"/>
          <prop k="color" v="0,0,0,0"/>
          <prop k="outline_color" v="255,220,0,255"/>
          <prop k="outline_width" v="0.6"/>
          <prop k="outline_style" v="solid"/>
          <prop k="size" v="3.2"/>
          <prop k="size_unit" v="MM"/>
        </layer>
      </symbol>
      <symbol type="marker" name="2" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <prop k="name" v="circle"/>
          <prop k="color" v="0,0,0,0"/>
          <prop k="outline_color" v="255,140,0,255"/>
          <prop k="outline_width" v="0.7"/>
          <prop k="outline_style" v="solid"/>
          <prop k="size" v="3.4"/>
          <prop k="size_unit" v="MM"/>
        </layer>
      </symbol>
      <symbol type="marker" name="3" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <prop k="name" v="circle"/>
          <prop k="color" v="0,0,0,0"/>
          <prop k="outline_color" v="230,0,0,255"/>
          <prop k="outline_width" v="0.8"/>
          <prop k="outline_style" v="solid"/>
          <prop k="size" v="3.6"/>
          <prop k="size_unit" v="MM"/>
        </layer>
      </symbol>
    </symbols>
    <classificationMethod id="Custom"/>
  </renderer-v2>
  <layerGeometryType>0</layerGeometryType>
</qgis>
