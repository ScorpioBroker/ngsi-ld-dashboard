import datetime
import json
import logging
import os
import random
import sys
import time
import requests
from dash import Dash, dcc, html, Input, Output, State, dash_table, ALL, callback_context
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import time
import math
import base64
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash_extensions.javascript import assign
import numbers
from dash.exceptions import PreventUpdate
import dash_cytoscape as cyto

LOGGER = logging.getLogger("ngsildmap")
LOGGER.setLevel(10)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
sh.setLevel(10)
LOGGER.addHandler(sh)
LOGGER.info("NGSI-LD Map starting...")
image_filename = 'assets/logo.png' # replace with your own image
f = open(image_filename, 'rb')
encoded_image = base64.b64encode(f.read())
f.close()
cyto.load_extra_layouts()
hide_query_config = False
queries = []
if os.path.exists('queries.json'):
  f = open('queries.json')
  queries = json.load(f)
  f.close()
  hide_query_config = True

#scorpio_host = os.getenv('DASH_SCORPIO_HOST', 'http://localhost:49090')
scorpio_host = os.getenv('DASH_SCORPIO_HOST', 'http://192.168.42.236:9090')
header_title = os.getenv('DASH_SCORPIO_HEADER_TITLE', 'City Livability Index Flexibe Frontend')
query_title = os.getenv('DASH_SCORPIO_QUERY_TITLE', 'Indexes')
server_port = int(os.getenv('DASH_SCORPIO_QUERY_TITLE', '9999'))
atcontext_link = {'Link': '<'+ os.getenv('DASH_ATCONTEXT', 'https://raw.githubusercontent.com/smart-data-models/data-models/master/context.jsonld') +'>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'}
chroma = "https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js"  # js lib used for colors
app = Dash(external_scripts=[chroma], prevent_initial_callbacks=True, external_stylesheets=[dbc.themes.DARKLY])

def formatToolTip(tooltipvalue):
  if len(tooltipvalue) <= 80:
    return '<br>'.join(tooltipvalue[i:i+80] for i in range(0, len(tooltipvalue), 80))
  return tooltipvalue


@app.callback(
  Output('type-input', 'value'),
  Output('attribute-input', 'value'),
  Output('entity-type-selection', 'data'),
  Output('entity-type-selection', 'page_current'),
  Input('type-attriute-button', 'n_clicks'),
  State('type-input', 'value'),
  State('attribute-input', 'value'),
  State('entity-type-selection', 'data'),
  State('entity-type-selection', 'page_size'))
def addEntityType(n, newType, newAttrib, typeAttribRows, pageSize):
  if n:
    typeAttribRows.append({"type": newType,"attrib": newAttrib})
    newType = ''
    newAttrib = ''
    return newType, newAttrib, typeAttribRows, math.ceil(len(typeAttribRows)/pageSize) - 1
  return newType, newAttrib, typeAttribRows, 0
@app.callback(
  Output('query-table', 'data', allow_duplicate=True),
  Input('add-query-button', 'n_clicks'),
  State('entity-type-selection', 'derived_virtual_selected_rows'),
  State('entity-type-selection', 'data'),
  State('query-table', 'data'),
  State('query-name-input', 'value'),
  State('q-input', 'value'))
def addQuery(n, selectedRows, data, queries, queryName, q):
  if n:
    found = None
    for entry in queries:
      if 'name' in entry and entry['name'] == queryName:
        found = entry
        break
    if found:
      queries.remove(found)
    query = {'name': queryName}
    query['highlight-attrib'] = data[selectedRows[0]]['attrib']
    query['type'] = data[selectedRows[0]]['type']
    if q:
      query['q'] = q
    queries.append({'name': queryName, 'query': query})
    print(json.dumps(queries))
  return queries

@app.callback(
  Output('entities-table', 'data'),
  Output('layer-control', 'children'),
  Output('entity-graph', 'elements', allow_duplicate= True),
  Input('query-table', 'data'))
def updateData(queries):
  entityTableResult = []
  geoJsonLayers = []
  entityGraph = []
  if queries:
    colorscale = ['red', 'yellow', 'green', 'blue', 'purple']
    style = dict(weight=2, opacity=1, color='white', dashArray='3', fillOpacity=0.7)
    # Geojson rendering logic, must be JavaScript as it is executed in clientside.
    style_handle = assign("""function(feature, context){
      const {min, max, colorscale, style, colorProp} = context.hideout;  // get props from hideout
      const value = feature.properties[colorProp];  // get value the determines the color
      const csc = chroma.scale(colorscale).domain([min, max]);
      style.fillColor = csc(value); // set the fill color according to the class
      return style;
    }""")
    point_to_layer = assign("""function(feature, latlng, context){
      console.log(context);
      const min = context.hideout.min;
      const max = context.hideout.max;
      const colorscale = context.hideout.colorscale;
      const circleOptions = context.hideout.circleOptions;
      const colorProp = context.hideout.colorProp;
      const csc = chroma.scale(colorscale).domain([min, max]);  // chroma lib to construct colorscale
      circleOptions.fillColor = csc(feature.properties[colorProp]);  // set color based on color prop
      return L.circleMarker(latlng, circleOptions);  // render a simple circle marker
    }""")
    on_each_feature = assign("""function(feature, layer, context){
      layer.bindTooltip(`${feature.properties.tooltip}`)
    }""")
    mapLayers = {}
    for query in queries:
      name = query['name']
      valueAttrib = query['query']['highlight-attrib']
      q = None
      if 'q' in query['query']:
        q = query['query']['q']
      entities = getEntities(query['query'])
      mapLayers[name] = {'geoJson': [], 'value': [], 'metadata': [], 'id': []}
      queryMin = 9999999999999999999999
      queryMax = -9999999999999999999999
      for entity in entities:
        entityId = entity["id"]
        entityTypes = entity["type"]
        entityGraph.append({'data': {'id': entityId, 'label': entityId + ' ' + str(entityTypes), 'type': 'entity'}, 'classes': 'entity'})
        if type(entityTypes) == list:
          entityTypes = ','.join(entityTypes)
        del entity["id"]
        del entity["type"]
        containsLocation = 'location' in entity.keys()
        metaData = ''
        rels = {}
        foundItem = False
        for key,values in entity.items():
          if type(values) != list:
            values = [values]
          for value in values:
            if type(value) != dict:
              continue
            graphId = entityId + key
            if 'value' in value.keys():
              valueStr = value['value']
              if 'datasetId' in value:
                graphId += value['datasetId']
              entityGraph.append({'data': {'id': graphId, 'label': str(valueStr), 'type': 'prop'}, 'classes': 'property'})
              entityGraph.append({'data': {'source': entityId, 'target': graphId, 'label': key}, 'classes': 'propertyedge'})
            elif 'object' in value.keys():
              valueStr = value['object']
              if 'datasetId' in value:
                graphId += value['datasetId']
              if type(valueStr) == list:
                for rel in valueStr:
                  entityGraph.append({'data': {'id': graphId+rel, 'label': str(rel), 'type': 'rel'}, 'classes': 'relationship'})
                  entityGraph.append({'data': {'source': entityId, 'target': graphId + rel, 'label': key}, 'classes': 'relationshipedge'})
                  if rel not in rels:
                    rels[rel] = [key]
                  else:
                    rels[rel].append(key)
              else:
                entityGraph.append({'data': {'id': graphId+valueStr, 'label': str(valueStr), 'type': 'rel'}, 'classes': 'relationship'})
                entityGraph.append({'data': {'source': entityId, 'target': graphId + valueStr, 'label': key}, 'classes': 'relationshipedge'})
                if valueStr not in rels:
                  rels[valueStr] = [key]
                else:
                  rels[valueStr].append(key)
            else:
              continue
            if containsLocation:
              if key == 'location':
                mapLayers[name]['geoJson'].append({'id': entityId, 'type': 'Feature', 'geometry': value['value']})
              elif key == valueAttrib:
                if isinstance(valueStr, numbers.Number):
                  mapLayers[name]['value'].append(valueStr)
                  foundItem = True
                  if valueStr < queryMin:
                    queryMin = valueStr
                  if valueStr > queryMax:
                    queryMax = valueStr
                else:
                  queryMin = 1
                  queryMax = 1
                  mapLayers[name]['value'].append(1)
                metaData += '<b>' + key + ': </b>' + formatToolTip(str(valueStr)) + '<br>'
              else:
                metaData += key + ': ' + formatToolTip(str(valueStr)) + '<br>'
            valueStr = str(valueStr)
            entityTableResult.append({'entityId': entityId, 'entityType': entityTypes, 'attrib': key, 'attrib_value': valueStr, 'relationship': str(value['type'] == 'Relationship')})
        if containsLocation:
          metaData = '<h5>' + entityId + '</h5><br>' + metaData
          mapLayers[name]['metadata'].append(metaData)
          mapLayers[name]['id'].append(entityId)
          if 'min' in query and 'max' in query:
            mapLayers[name]['minmax'] = {'min': query['min'], 'max': query['max']}
          else:
            mapLayers[name]['minmax'] = {'min': queryMin, 'max': queryMax}
          mapLayers[name]['geoJson'][-1]['properties'] = entity
          if foundItem:
            entity['value'] = mapLayers[name]['value'][-1]
          else:
            entity['value'] = -1
          entity['tooltip'] = metaData
          entity['rels'] = rels
          entity['id'] = entityId
          entity['type'] = entityTypes
    i = 0
    for key, value in mapLayers.items():
      if len(value['geoJson']) == 0:
        continue
      geoJson = {'type': 'FeatureCollection', 'features': value['geoJson']}
      geoJsonLayers.append(dl.Overlay(dl.GeoJSON(data=geoJson, zoomToBounds = True, style=style_handle, pointToLayer=point_to_layer, onEachFeature=on_each_feature, hideout=dict(min=value['minmax']['min'], max=value['minmax']['max'], colorscale=colorscale, style=style, colorProp="value", circleOptions=dict(fillOpacity=1, stroke=False, radius=5)), id={"type": "geo-json-layer", "index": i}),name=key, checked=True))
      i += 1
    #return entityTableResult, dl.Overlay(dl.GeoJSON(data=geoJson, zoomToBounds = True),name=key, checked=True)

  #print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')
  #print(str(entityGraph))
  return entityTableResult, geoJsonLayers, entityGraph

@app.callback(
  Output('entity-graph', 'elements', allow_duplicate= True),
  Input('entity-graph', 'tapNodeData'),
  State('entity-graph', 'elements'))
def handleNodeTap(tapData, graphData):
  #print(str(tapData))
  if tapData['type'] == 'rel':
    global scorpio_host
    global atcontext_link
    response = requests.get(scorpio_host + '/ngsi-ld/v1/entities/' + tapData['label'], headers=atcontext_link)
    nodeId = tapData['id']
    found = (response.status_code == 200)
    resultData = []
    nodeFound = False
    edgeFound = False
    newEdge = None
    #print(str(found))
    knownEntityIds = set()
    for dataEntry in graphData:
      #print(str(dataEntry))
      if 'type' in dataEntry['data'] and dataEntry['data']['type'] == 'entity':
        knownEntityIds.add(dataEntry['data']['id'])
      if 'id' in dataEntry['data'].keys():
        if dataEntry['data']['id'] == nodeId:
          if not found:
            #print('setting node dead ' + nodeId)
            dataEntry['classes'] = 'deadrelationshipedge'
            resultData.append(dataEntry)
 #         else:
            #print('removing node ' + nodeId)
        else:
          resultData.append(dataEntry)
      if 'target' in dataEntry['data'].keys():
        #print(str(dataEntry))
        #print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        if dataEntry['data']['target'] == nodeId:
          if found:
            dataEntry['classes'] = 'aliverelationshipedge'
            dataEntry['data']['target'] = tapData['label']
            #print('setting edge ' + nodeId)
            #print(str(dataEntry))
            newEdge = dataEntry
          else:
            dataEntry['classes'] = 'deadrelationshipedge'
            #print('setting edge dead' + nodeId)
            #print(str(dataEntry))
            resultData.append(dataEntry)
        else:
          resultData.append(dataEntry)
    if found:
      entity = response.json()
      entityId = entity['id']
      resultData.append({'data': {'id': entityId, 'label': entityId + ' ' + str(entity['type']), 'type': 'entity'}, 'classes': 'entity'})
      del newEdge['data']['id']
      resultData.append(newEdge)
      del entity["id"]
      del entity["type"]
      print('knownEntityIds ' + str(knownEntityIds))
      for key,values in entity.items():
        if type(values) != list:
          values = [values]
        for value in values:
          if type(value) != dict:
            continue
          graphId = entityId + key
          if 'value' in value.keys():
            valueStr = value['value']
            if 'datasetId' in value:
              graphId += value['datasetId']
            resultData.append({'data': {'id': graphId, 'label': str(valueStr), 'type': 'prop'}, 'classes': 'property'})
            resultData.append({'data': {'source': entityId, 'target': graphId, 'label': key}, 'classes': 'propertyedge'})
          elif 'object' in value.keys():
            valueStr = value['object']
            if 'datasetId' in value:
              graphId += value['datasetId']
            if type(valueStr) == list:
              for rel in valueStr:
                if str(rel) in knownEntityIds:
                  #print('knownId ' + str(rel))
                  #print('target ' + str(rel))
                  #print('source ' + str(entityId))
                  #print('relname ' + key)
                  resultData.append({'data': {'source': entityId, 'target': rel, 'label': key}, 'classes': 'aliverelationshipedgeback'})
                else:
                  resultData.append({'data': {'id': graphId+rel, 'label': str(rel), 'type': 'rel'}, 'classes': 'relationship'})
                  resultData.append({'data': {'source': entityId, 'target': graphId + rel, 'label': key}, 'classes': 'relationshipedge'})
            else:
              if str(valueStr) in knownEntityIds:
                #print('knownId ' + str(valueStr))
                #print('target ' + str(valueStr))
                #print('source ' + str(entityId))
                #print('relname ' + key)
                resultData.append({'data': {'source': entityId, 'target': str(valueStr), 'label': key}, 'classes': 'aliverelationshipedgeback'})
              else:
                resultData.append({'data': {'id': graphId+valueStr, 'label': str(valueStr), 'type': 'rel'}, 'classes': 'relationship'})
                resultData.append({'data': {'source': entityId, 'target': graphId + valueStr, 'label': key}, 'classes': 'relationshipedge'})
  #print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
  #print(json.dumps(resultData))  
  return resultData
  
@app.callback(
  Output('entity-popup', 'is_open', allow_duplicate=True),
  Output('entity-popup-header', 'children', allow_duplicate=True),
  Output('entity-popup-body', 'children', allow_duplicate=True),
  Input('entity-relationships', 'clickData'))
def handleRelClick(clickData):
  #print(str(clickData))
  tmp = clickData['points'][0]
  if len([i for i, letter in enumerate(tmp['currentPath']) if letter == '/']) != 2:
    raise PreventUpdate
  entityId = tmp['label']
  return showEntity(1, {'props': {'children': entityId}})
  
def getValueLabels(value, rels, key):
  result = []
  if type(value) == list:
    for entry in value:
      result.append(Html.Div(getValueLabels()))
  elif type(value) == dict:
    propType = value['type']
    if propType == 'Property':
      label = value['value']
      del value['value']
      if 'unitCode' in value:
        label += ' ' + value['unitCode']
        del value['value']
      if 'datasetId' in value:
        label += '<br>datasetId: '  + value['datasetId']
        del value['datasetId']
      result.append(dbc.Button(label, id={"type": "entity-prop", "index": key}, disabled=True, style={'background-color': 'grey', 'border': 'none'}))
    elif propType == 'Relationship':
      if type(value['object']) != list:
        entryRels = [value['object']]
      else:
        entryRels = value['object']
      datasetId = None
      if 'datasetId' in value:
        datasetId = '<br>datasetId: ' + value['datasetId']
      for entryRel in entryRels:
        label = entryRel
        if datasetId:
          label += datasetId
        if entryRel in rels.keys():
          result.append(dbc.Button(label, id={"type": "entity-rel", "index": entryRel}, disabled=True, style={'background-color': 'grey', 'border': 'none'}))
        else:
          result.append(dbc.Button(label, disabled=True, style={'background-color': 'grey', 'border': 'none'}))
  else:
    result.append(dbc.Button(str(value), disabled=True, style={'background-color': 'grey', 'border': 'none'}))
  return result

@app.callback(
    Output("entity-relationships", "figure"),
    Output("entity-details", "children"),
    Output("entity-details-header", "children"),
    Input({"type": "geo-json-layer", "index": ALL}, "n_clicks"),
    State({"type": "geo-json-layer", "index": ALL}, "clickData"))
def geoLayerClick(n, data):
  resultData = []
  entityDetailsChildren = []
  entityDetailsHeader = "Please select an entity"
  onlyNone = True
  for i in n:
    if i != None:
      onlyNone = False
      break
  if not onlyNone:
    index = callback_context.triggered_id['index']
    properties = data[index]['properties']
    rels = properties['rels']
    entityId = properties['id']
    rel2entities = getEntitiesById(rels)
    for key, value in rel2entities.items():
      for entity in value:
        resultData.append({'rel': key, 'target': entity['id'], 'entity': entity, 'values': 1, 'entityId': entityId})
    selectedEntity = properties
    del selectedEntity['tooltip']
    del selectedEntity['value']
    del selectedEntity['rels']
    entityDetailsHeader = dbc.Button(html.H5(selectedEntity['id']), id='show-entity-button', style={'background-color': 'grey', 'border': 'none'})
    entityDetailsChildren.append(html.Div([dbc.Button(html.B("type: "), disabled=True, style={'background-color': 'grey', 'border': 'none'}), dbc.Button(selectedEntity['type'], disabled=True, style={'background-color': 'grey', 'border': 'none'})]))
    del selectedEntity['type']
    
    del selectedEntity['id']
    del selectedEntity['cluster']
    for key, value in selectedEntity.items():
      divData = []
      divData.append(dbc.Button(html.B(key + ': '), id={"type": "entity-attrib-name", "index": entityId + '?attrs=' + key}, style={'background-color': 'grey', 'border': 'none'}))
      divData.extend(getValueLabels(value, rels, key))
      if len(divData) > 1:
        entityDetailsChildren.append(html.Div(divData))
  else:
    resultData.append({'rel': 'an', 'target': 'Select', 'entity': {'dummy': 'asdsadas'}, 'values': 1, 'entityId': 'entity id'})
  print(str(resultData))
  if len(resultData) == 0:
    resultData.append({'rel': 'Relationship', 'target': 'No', 'entity': {'dummy': 'asdsadas'}, 'values': 1, 'entityId': 'found'})
  fig = px.sunburst(data_frame=resultData, path=['entityId', 'rel', 'target'], values='values', template='plotly_dark')
  fig.update_layout(margin=dict(t=0, l=0, r=0, b=0), plot_bgcolor='grey', paper_bgcolor='grey')
  return fig, entityDetailsChildren, entityDetailsHeader

@app.callback(
    Output('attrib-popup', 'is_open'),
    Output('attrib-popup-body', 'children', allow_duplicate=True),
    Output('attrib-popup-header', 'children'),
    Input({"type": "entity-attrib-name", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def handleAttribNameClick(n):
  onlyNone = True
  for i in n:
    if i != None:
      onlyNone = False
      break
  if not onlyNone:
    index = callback_context.triggered_id['index']
    now = datetime.datetime.now()
    before = now - datetime.timedelta(days=720)
    timeFrame = 'timerel=between&timeproperty=observedAt&timeAt=' + before.strftime('%Y-%m-%dT%H:%M:%SZ') + '&endTimeAt=' + now.strftime('%Y-%m-%dT%H:%M:%SZ')
    splittedIndex = index.split('?attrs=')
    return True, getAttribBody(index, timeFrame, now, before), [splittedIndex[0] + ' - ' + splittedIndex[1]]
  return False, [], []
  
def getAttribBody(index, timeFrame, now, before):
  global scorpio_host
  global atcontext_link
  print('tempAggrQuery')
  print(scorpio_host + '/ngsi-ld/v1/temporal/entities/' + index + '&aggrMethods=max,min,avg,sum,sumsq,stddev,totalCount,distinctCount&' + timeFrame)
  print('tempDataQuery')
  print(scorpio_host + '/ngsi-ld/v1/temporal/entities/' + index + '&options=sysAttrs&' + timeFrame)
  tempAggr = requests.get(scorpio_host + '/ngsi-ld/v1/temporal/entities/' + index + '&aggrMethods=max,min,avg,sum,sumsq,stddev,totalCount,distinctCount&' + timeFrame, headers=atcontext_link).json()
  tempValues = requests.get(scorpio_host + '/ngsi-ld/v1/temporal/entities/' + index + '&options=sysAttrs&' + timeFrame, headers=atcontext_link).json()
  body = []
  aggrData = []
  for key, attribAggr in tempAggr.items():
    if type(attribAggr) != dict:
      continue
    attrKeys = attribAggr.keys()
    if 'min' in attrKeys:
      aggrData.append({'x': 'Min', 'y': attribAggr['min'][0][0], 'attribute': key})
    if 'max' in attrKeys:
      aggrData.append({'x': 'Max', 'y': attribAggr['max'][0][0], 'attribute': key})
    if 'avg' in attrKeys:
      aggrData.append({'x': 'Average', 'y': attribAggr['avg'][0][0], 'attribute': key})
    if 'sum' in attrKeys:
      aggrData.append({'x': 'Sum', 'y': attribAggr['sum'][0][0], 'attribute': key})
    #if 'sumsq' in attrKeys:
      #aggrData.append({'x': 'Sum squared', 'y': attribAggr['sumsq'][0][0], 'attribute': key})
    if 'stddev' in attrKeys:
      aggrData.append({'x': 'Std Dev', 'y': attribAggr['stddev'][0][0], 'attribute': key})
    if 'totalCount' in attrKeys:
      aggrData.append({'x': 'Total count', 'y': attribAggr['totalCount'][0][0], 'attribute': key})
    if 'distinctCount' in attrKeys:
      aggrData.append({'x': 'Distinct count', 'y': attribAggr['distinctCount'][0][0], 'attribute': key})
    #{'x': 'Sum squared', 'y': sumsqData},
  valueData = []
  tableData = {}
  tableHeader = []
  tableHeader.append({'name': 'Timestamp', 'id': 'timestamp', 'selectable': False})
  for key, attribValues in tempValues.items():
    if type(attribValues) != list and type(attribValues) != dict:
      continue
    tableHeader.append({'name': key, 'id': key, 'selectable': False})
    tableHeader.append({'name': 'instance id', 'id': key+'instanceId', 'selectable': False})
    if type(attribValues) != list:
      attribValues = [attribValues]
    for entry in attribValues:
      if 'value' in entry:
        entryValue = entry['value']
        if 'observedAt' in entry.keys():
          dateTime = entry['observedAt']
        else:
          dateTime = entry['modifiedAt']
        if dateTime not in tableData.keys():
          tableData[dateTime] = {}
        tableData[dateTime][key] = {'value': str(entryValue), 'instanceId': entry['instanceId']}
        if isinstance(entryValue, numbers.Number):
          valueData.append({'x': dateTime, 'y': entry['value'], 'attribute': key})
      elif 'object' in entry:
        entryValue = entry['object']
        if 'observedAt' in entry.keys():
          dateTime = entry['observedAt']
        else:
          dateTime = entry['modifiedAt']
        if dateTime not in tableData:
          tableData[dateTime] = {}
        tableData[dateTime][key] = {'value': str(entryValue), 'instanceId': entry['instanceId']}
    #print(str(aggrData))
  realTableData = []
  for key, value in tableData.items():
    tmp = {'timestamp': key}
    for key1, value1 in value.items():
      tmp[key1] = value1['value']
      tmp[key1+'instanceId'] = value1['instanceId']
    realTableData.append(tmp)
  
  #print(str(df2))
  
  body.append(dbc.Label(index, id='shown-attrib', hidden=True))
  body.append(html.Div([dcc.DatePickerRange(month_format='MMM Do, YY', id='date-picker-attrib'), dbc.Button('Refresh', id='attrib-reload')]))
  if len(aggrData) > 0:
    df2 = pd.DataFrame(data=aggrData)
    aggrChart = px.bar(df2, title='Aggregation Data', template='plotly_dark', x='x', y='y', color='attribute', barmode='group',)
    aggrChart.update_xaxes(title=None, visible=True, showticklabels=True)
    aggrChart.update_yaxes(title=None, visible=True, showticklabels=True)
    aggrChart.update_layout(uirevision = 'something', plot_bgcolor='grey', paper_bgcolor='grey')#, paper_bgcolor='grey', plot_bgcolor='darkgrey')    
    body.append(dcc.Graph(figure=aggrChart, style={'display': 'inline-block', 'width': '100%'}, id='aggr-chart'))
  if len(valueData) > 0:
    df = pd.DataFrame(data=valueData)
    histGraph = px.line(df, x='x', y='y', markers=True, template='plotly_dark',  title='History Data', color='attribute')
    histGraph.update_xaxes(title=None, visible=True, showticklabels=True)
    histGraph.update_yaxes(title=None, visible=True, showticklabels=True)
    histGraph.update_layout(plot_bgcolor='grey', paper_bgcolor='grey')
    body.append(dcc.Graph(figure=histGraph, style={'display': 'inline-block', 'width': '100%'}, id='hist-chart'))
  body.append(dash_table.DataTable(
    columns=tableHeader,
    data=realTableData,
    page_size=11,
    style_header={
      'backgroundColor': 'grey',
      'border': '1px solid black',
      'textAlign': 'left'
    },
    style_data={
      'backgroundColor': 'darkgrey',
      'border': '1px solid black',
      'textAlign': 'left',
      'whiteSpace': 'normal',
      'height': 'auto',
    },
    style_cell={
      'overflow': 'hidden',
      'textOverflow': 'ellipsis',
      'maxWidth': 0
    },
    css=[
      {'selector': '.dash-table-tooltip',
       'rule': 'background-color: grey; color: white;',
      }
    ],
    tooltip_data=realTableData,
    tooltip_delay=0,
    tooltip_duration=None
  ))
  return body

@app.callback(
  Output('entity-graph-popup', 'is_open'),
  Input('entity-graph-button', 'n_clicks'))
def showGraph(n):
  return True

@app.callback(
    Output('attrib-popup-body', 'children'),
    Input('attrib-reload', 'n_clicks'),
    State('date-picker-attrib', 'start_date'),
    State('date-picker-attrib', 'end_date'),
    State('shown-attrib', 'children'),
    prevent_initial_call=True)
def reloadAttrib(n, start, end, index):
  if n:
    print(str(start))
    print(str(end))
    start = datetime.datetime.strptime(start, '%Y-%m-%d')
    end = datetime.datetime.strptime(end, '%Y-%m-%d')
    print(str(start))
    print(str(end))
  else:
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=720)
  timeFrame = 'timerel=between&timeproperty=observedAt&timeAt=' + start.strftime('%Y-%m-%dT%H:%M:%SZ') + '&endTimeAt=' + end.strftime('%Y-%m-%dT%H:%M:%SZ')
  return getAttribBody(index, timeFrame, end, start)

@app.callback(
    Output('entity-popup', 'is_open', allow_duplicate=True),
    Output('entity-popup-header', 'children', allow_duplicate=True),
    Output('entity-popup-body', 'children', allow_duplicate=True),
    Input('show-entity-button', 'n_clicks'),
    State('show-entity-button', 'children'),
    prevent_initial_call=True)  
def showEntity(n, entityId):
  if n:
    global scorpio_host
    global atcontext_link
    entityId = entityId['props']['children']
    index = entityId + '?dummy=1'
    now = datetime.datetime.now()
    before = now - datetime.timedelta(days=720)
    timeFrame = 'timerel=between&timeproperty=observedAt&timeAt=' + before.strftime('%Y-%m-%dT%H:%M:%SZ') + '&endTimeAt=' + now.strftime('%Y-%m-%dT%H:%M:%SZ')
    liveEntity = requests.get(scorpio_host + '/ngsi-ld/v1/entities/'+entityId+'?options=sysAttrs', headers=atcontext_link).json()
    liveTableData = []
    for key, value in liveEntity.items():
      if type(value) != list:
        value = [value]
      for valueEntry in value:
        if type(valueEntry) == dict:
          if valueEntry['type'] == 'Property':
            toShowValue = valueEntry['value']
            if 'unitCode' in valueEntry:
              unitCode = valueEntry['unitCode']
            else:
              unitCode = ''
          elif valueEntry['type'] == 'Relationship':
            toShowValue = valueEntry['object']
            unitCode = ''
          elif valueEntry['type'] == 'GeoProperty':
            toShowValue = valueEntry['value']['coordinates']
            unitCode = valueEntry['value']['type']
          else:
            continue
          modifiedAt = valueEntry['modifiedAt']
          if 'datasetId' in valueEntry.keys():
            datasetId = valueEntry['datasetId']
          else:
            datasetId = ''
          liveTableData.append({'attribName': key, 'attribValue': json.dumps(toShowValue), 'unitCode': unitCode, 'modifiedAt': modifiedAt, 'datasetId': datasetId})
        else:
          liveTableData.append({'attribName': key, 'attribValue': str(valueEntry), 'unitCode': '', 'modifiedAt': '', 'datasetId': ''})
    tableHeader = []
    tableHeader.append({'name': 'Name', 'id': 'attribName', 'selectable': False})
    tableHeader.append({'name': 'Value', 'id': 'attribValue', 'selectable': False})
    tableHeader.append({'name': 'Unit type', 'id': 'unitCode', 'selectable': False})
    tableHeader.append({'name': 'Last change', 'id': 'modifiedAt', 'selectable': False})
    tableHeader.append({'name': 'Dataset ID', 'id': 'datasetId', 'selectable': False})
    
    body = []
    
    body.append(html.H4('Attributes'))
    body.append(dash_table.DataTable(
      columns=tableHeader,
      data=liveTableData,
      column_selectable=None,
      editable=False,
      page_size=11,
      style_header={
        'backgroundColor': 'grey',
        'border': '1px solid black',
        'textAlign': 'left'
      },
      style_data={
        'backgroundColor': 'darkgrey',
        'border': '1px solid black',
        'textAlign': 'left'
      },
      style_cell={
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
        'maxWidth': 0
      }
    ))
    body.append(html.H4('Temporal Data'))
    body.extend(getAttribBody(index, timeFrame, now, before))
    return True, [entityId], body
  return False, [], []
def get_type_attrib_selection():
  result = []
  global scorpio_host
  global atcontext_link
  types = requests.get(scorpio_host + '/ngsi-ld/v1/types?details=true', headers=atcontext_link).json()
  for entity_type in types:
    for attrib in entity_type["attributeNames"]:
      result.append({'type': entity_type['typeName'], 'attrib': attrib})
  return result

def getInitialSunburst():
  data = [{'rel': 'an', 'target': 'select', 'entity': {}, 'values': 1, 'entityId': 'entity'}]
  fig = px.sunburst(data, path=['entityId', 'rel', 'target'], values='values',template='plotly_dark')
  fig.update_layout(margin=dict(t=0, l=0, r=0, b=0), plot_bgcolor='grey', paper_bgcolor='grey')
  return fig

def initLoad():
  global hide_query_config
  if not hide_query_config:
    return []
  global queries
  return queries

def getEntities(query):
  global scorpio_host
  global atcontext_link
  params = {"limit": 1000}
  params['type'] = query['type']
  
  if 'q' in query:
    params['q'] = query['q']
  if 'id' in query:
    params['id'] = query['id']
  if 'idPattern' in query:
    params['idPattern'] = query['idPattern']

  url = scorpio_host + "/ngsi-ld/v1/entities"
  req = requests.get(url, params, headers=atcontext_link)
  return req.json()

def getEntitiesById(rels):
  global scorpio_host
  global atcontext_link
  ids = ','.join(rels.keys())
  qResult = requests.get(scorpio_host + '/ngsi-ld/v1/entities?id=' + ids, headers=atcontext_link).json()
  result = {}
  for entity in qResult:
    attribNames = rels[entity['id']]
    for attribName in attribNames:
      if attribName in result:
        result[attribName].append(entity)
      else:
        result[attribName] = [entity]
  return result


#initialSetup(app)
entity_table_data, geo_layers, entity_graph_data = updateData(queries)
app.layout = html.Div([
    html.Div([
      html.Img(src='data:image/png;base64,{}'.format(encoded_image.decode()), style={'display': 'inline-block', 'height': '80px'}),
      html.H2(header_title, style={'display': 'inline-block', 'padding-left': 2, 'vertical-align': 'middle', 'height': '50'}),
      dbc.Label("", width="auto", id='dummy')
    ], id='header_div', style={'text-align': 'center', 'padding': 5}),
    html.Div([
      html.Div([
        html.Div([
          dbc.Form(
            dbc.Row(
              [
                dbc.Label("Type", width="auto"),
                dbc.Col(
                  dbc.Input(type="text", placeholder="Enter entity type", id="type-input"),
                  className="me-3",
                ),
                dbc.Label("Attribute name", width="auto"),
                dbc.Col(
                  dbc.Input(type="text", placeholder="Enter attribute name", id="attribute-input"),
                  className="me-3",
                ),
                dbc.Col(dbc.Button("Add type", color="primary", id="type-attriute-button"), width="auto"),
              ],
              className="g-2",
            )
          ),
          dash_table.DataTable(
            id='entity-type-selection',
            columns=[
              {
                'name': 'Entity Type',
                'id': 'type',
                'selectable': False
              },
              {
                'name': 'Attribute Name',
                'id': 'attrib',
                'selectable': False
              }
            ],
            data=get_type_attrib_selection(),
            row_selectable="single",
            column_selectable=None,
            editable=False,
            page_size=11,
            style_header={
              'backgroundColor': 'grey',
              'border': '1px solid black',
              'textAlign': 'left'
            },
            style_data={
              'backgroundColor': 'darkgrey',
              'border': '1px solid black',
              'textAlign': 'left'
            },
            style_cell={
              'overflow': 'hidden',
              'textOverflow': 'ellipsis',
              'maxWidth': 0
            }
          ),
          dbc.Form(
            dbc.Row(
              [
                dbc.Label("Name", width="auto"),
                dbc.Col(
                  dbc.Input(type="text", placeholder="Enter a query name", id="query-name-input"),
                  className="me-3",
                ),
                dbc.Label("Q query", width="auto"),
                dbc.Col(
                  dbc.Input(type="text", placeholder="Enter attribute name", id="q-input"),
                  className="me-3",
                ),
                dbc.Col(dbc.Button("Add Query", color="primary", id="add-query-button"), width="auto"),
              ],
              className="g-2",
            )
          )
        ],hidden=hide_query_config),
        html.Div([
          dash_table.DataTable(
            id='query-table',
            columns=[
              {
                'name': query_title,
                'id': 'name',
                'selectable': False
              }
            ],
            data=initLoad(),
            row_deletable=True,
            column_selectable=None,
            editable=False,
            page_size=11,
            style_header={
              'backgroundColor': 'grey',
              'border': '1px solid black',
              'textAlign': 'left'
            },
            style_data={
              'backgroundColor': 'darkgrey',
              'border': '1px solid black',
              'textAlign': 'left'
            },
            style_cell={
              'overflow': 'hidden',
              'textOverflow': 'ellipsis',
              'maxWidth': 0
            }
          )
          #dbc.Button('Show Entity Graph', id='entity-graph-button', color="primary")
        ], style={'width': '100%'})
      ], style={'width': '24vw', 'display': 'inline-block', 'vertical-align': 'top', 'padding': '2px'}),
      html.Div([
        dl.Map([
            dl.TileLayer(),
            dl.LayersControl(geo_layers, id='layer-control')
          ],
          center=[49,9], zoom=6, style={'height': '84vh'}) #, style={'height': '85vh'}
      ], id='entities_map_container', style={'width': '50vw', 'display': 'inline-block', 'vertical-align': 'top', 'padding': '2px'}),
      html.Div([
        dcc.Graph(
          id='entity-relationships',
          figure=getInitialSunburst(),
        ),
        html.Div([], style={'padding': '2px'}),
        html.Div([
          dbc.Label("Please select an entity", width='auto', id='entity-details-header'),
          html.Div([], id='entity-details')
        ], style={'background-color': 'grey', 'padding': '2px'})
      ], style={'width': '24vw', 'display': 'inline-block', 'vertical-align': 'top', 'padding': '2px'})
    ], id='type-selection-container', style={'width': '100vw', 'height': '85vh'}),
    html.Div([
      dash_table.DataTable(
          id='entities-table',
          columns=[
            {
              'name': 'Entity ID',
              'id': 'entityId',
              'selectable': False},
            {
              'name': 'Entity Type',
              'id': 'entityType',
              'selectable': False},          
            {
              'name': 'AttribName',
              'id': 'attrib',
              'selectable': False},
            {
              'name': 'Attrib Value',
              'id': 'attrib_value',
              'selectable': False},
            {
              'name': 'Relationship',
              'id': 'relationship',
              'selectable': False}
          ],
          data=entity_table_data,
          row_selectable="multi",
          column_selectable=None,
          editable=False,
          page_size=11,
          style_header={
            'backgroundColor': 'grey',
            'border': '1px solid black',
            'textAlign': 'left'
          },
          style_data={
            'backgroundColor': 'darkgrey',
            'border': '1px solid black',
            'textAlign': 'left',
            'whiteSpace': 'normal',
            'height': 'auto',
          },
          style_cell={
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
            'maxWidth': 0
          }
        )
    ], hidden=True, style={'width': '100vw', 'padding': '2px'}),
    dbc.Modal(
      [
        dbc.ModalHeader(dbc.ModalTitle("Header", id='attrib-popup-header'), close_button=True),
        dbc.ModalBody("This modal is vertically centered", id='attrib-popup-body'),
      ],
      id='attrib-popup',
      centered=True,
      is_open=False,
      scrollable=True,
      #fullscreen=True
      size='xl'
      #style={'float': 'middle'}
    ),
    dbc.Modal(
      [
        dbc.ModalHeader(dbc.ModalTitle("Header", id='entity-popup-header'), close_button=True),
        dbc.ModalBody("This modal is vertically centered", id='entity-popup-body'),
      ],
      id='entity-popup',
      centered=True,
      is_open=False,
      scrollable=True,
      fullscreen=True
      #size='xl'
      #style={'float': 'middle'}
    ),
    dbc.Modal(
      [
        dbc.ModalHeader(dbc.ModalTitle("Entity Graph", id='entity-graph-popup-header'), close_button=True),
        dbc.ModalBody([
          html.Div([
            cyto.Cytoscape(
              id='entity-graph',
              layout={'name': 'spread'},
              style={'width': '80vw', 'height': '80vh', 'background-color': 'white'},
              stylesheet=[
                {
                  'selector': '.entity',
                  'style': {
                    'text-color': 'orange',
                    'background-color': 'orange',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.propertyedge',
                  'style': {
                    'text-color': 'yellow',
                    'line-color': 'yellow',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.property',
                  'style': {
                    'text-color': 'yellow',
                    'background-color': 'yellow',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.relationshipedge',
                  'style': {
                    'text-color': 'green',
                    'line-color': 'green',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.relationship',
                  'style': {
                    'text-color': 'green',
                    'line-color': 'green',
                    'background-color': 'green',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.deadrelationshipedge',
                  'style': {
                    'text-color': 'red',
                    'line-color': 'red',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.aliverelationshipedge',
                  'style': {
                    'text-color': 'orange',
                    'line-color': 'orange',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.aliverelationshipedgeback',
                  'style': {
                    'curve-style': 'bezier',
                    'text-color': 'orange',
                    'line-color': 'orange',
                    'label': 'data(label)'
                  }
                },
                {
                  'selector': '.deadrelationship',
                  'style': {
                    'text-color': 'red',
                    'background-color': 'red',
                    'label': 'data(label)'
                  }
                }
              ],
              elements=entity_graph_data
            ),
            dbc.Label('', id='entity-graph-details')
          ])
        ], id='entity-graph-popup-body'),
      ],
      id='entity-graph-popup',
      centered=True,
      is_open=False,
      scrollable=True,
      fullscreen=True
      #size='xl'
      #style={'float': 'middle'}
    )
])



  


if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=server_port)
