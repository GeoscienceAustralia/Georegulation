###############################################################################
# Aim: Find ENC S57 data (.000 files), extract the every feature/geometry type combination or a user set
#      feature/geometry type from each of the ENC files into a single shapefile and attribute features as per the source
#      schema and add metadata from the S57 dataset including ENC name, ENC issue date, ENC comment and ENC scale.
#
#
# Each input ENC file containing a feature/geometry type of interest results in a shapefile named per the source
# S57 ENC file. The shapefiles are then combined into a composite shapefile which is labelled
# 'global'_FEATURETYPE_GEOMETRYTYPE.shp, e.g. 'global_ACHARE_POINT.shp', 'global_CBLSUB_LINESTRING.shp'.
#
# A folder is created at the same level as the input parent folder from which the script starts searching for .000 files.
# The folder contains the global shapefile, the Python script, a log file and a subfolder of the individual
# shapefiles, one for each input .000 file that contains the feature of interest.
# Useful open source Python reference https://livebook.manning.com/book/geoprocessing-with-python/chapter-3/126
#
# For S57 feature types see:
#   - https://iho.int/iho_pubs/standard/S-57Ed3.1/S-57%20Appendix%20B.1%20Annex%20A%20UOC%20Edition%204.1.0_Jan18_EN.pdf
#   - https://www.hydro.gov.au/prodserv/important-info/SPEC_05_55_AA34159_AUOC.pdf
#
#  Along with the feature/geometry type extractions the two pdf files above will be copied to the output folder, along
#  with this Python script and a log file detailing the processing.
#
#  An in memory layer is used between the source s57 data and the shapefile to enable transforming fields in the
#  s57 data that are not supported in shapefiles (integer list and string list field types). These fields
#  are converted to string field types and the content of the field is converted to a comma separated string.
#
# Duncan Moore (Duncan.Moore@ga.gov.au, Geoscience Australia), 2 February 2023

###############################################################################

# Import required libraries
from osgeo import ogr
from osgeo import osr
import os
import sys
import datetime
import time
import shutil
import logging as log
import urllib.request


def getENCMetadata(data):
    '''
    Parameters
    ----------
    data : TYPE osgeo.ogr.DataSource
        S57 ogr datasource

    Returns
    -------
    Dictionary including the name of the ENC (key='name'), issue date of the 
    ENC (key='issueDate'), scale of the ENC (key='scale') and a comment 
    describing the coverage of the ENC (key='comment')

    '''
    
    # Data set identification fields (DSID layer)
    layer = data.GetLayerByName('DSID')
    
    # Scale
    scale = 0
    # Datset name
    dsnm = ''
    # Comment on ENC spatial coverage
    comment = ''
    # Issue date of the ENC
    issueDate = ''
    
    for feature in layer:
        layerDefinition = layer.GetLayerDefn()
        for i in range(feature.GetFieldCount()):
            # print(layerDefinition.GetFieldDefn(i).GetName())
            # print(feature.GetField(i))
            if layerDefinition.GetFieldDefn(i).GetName() == 'DSPM_CSCL':
                scale = feature.GetField(i)
            elif layerDefinition.GetFieldDefn(i).GetName() == 'DSID_DSNM':
                dsnm = feature.GetField(i)
            elif layerDefinition.GetFieldDefn(i).GetName() == 'DSID_COMT':
                comment = feature.GetField(i)
            elif layerDefinition.GetFieldDefn(i).GetName() == 'DSID_ISDT':
                issueDate = feature.GetField(i)
            # print()
    if verbose:
        print(f'\nENC: {dsnm}, Issue date: {issueDate.encode("utf-8", "replace").decode()}, '
              f'Scale: 1:{scale}, comment: {comment.encode("utf-8", "replace").decode()}')
    return({'name':dsnm,'issueDate':issueDate,'scale':scale,'comment':comment})

def featureTypeGetter(encList):
    '''
    This function takes a list of paths to ENC files and returns a unique list of combinations of s57 feature types that
    exist across all the ENC sources.
    :param encList: List of paths to s57 ENC (.ooo) files
    :return: Unique list of feature type and geometry type (line, polygon, point) combinations that exist in the ENC
             sources
    '''
    s57Driver = ogr.GetDriverByName("S57")

    featureTypeDict = {}  # A dictionary is used for speed of use due to indexing.
    for e in encList:
        data = s57Driver.Open(e)
        for layer in data:
            if layer.GetName() not in featureTypeDict.keys():
                featureTypeDict[layer.GetName()] = 1  # the dictionary value here is inconsequential

    return list(featureTypeDict.keys())

def chartGetter(topFolder):
    '''

    :param topFolder:
    :return:
    '''
    chartList = []
    for root, folder, files in os.walk(topFolder):
        for f in files:
            # s57 data files end with a '000' extension.
            if f.endswith('000'):
                chartList.append(os.path.join(root, f))

    return chartList

# Set intial time
t0 = time.time()
# TODO: User to set printing to verbose for more print statements to support debugging
verbose = False

# The default is for s57 update files (e.g. .001, .002, .003, ..., .00N) to be applied to the .000 file that this script
# finds and reads. Applying updates is set to ensure updates are applied.
# https://gdal.org/drivers/vector/s57.html
os.environ["OGR_S57_OPTIONS"] = "UPDATES=ON"

# parentFolder from which all content within subfolders is searched for s57 data
parentFolder = input("Enter the top folder to search within for s57 (.000) data: ")
while not os.path.exists(f'{parentFolder}'):# Test to make sure an input was provided
    print('No existing top folder provided...')
    parentFolder = input("\tEnter the top folder: ")

# TODO: The user is required to identify the feature type to extract and the geometry type of that feature
# S57 feature type to extract: Consider Group 1 (higher priority) amongst Group 2 features
# 'CBLSUB': Submarine cables,
# 'CBLARE': Cable area
# 'PIPSOL': Pipelines - Submarine or on land
# 'PIPARE': Pipeline area
# 'COALNE': coastline (broken by shoreline construction ('SLCONS'), This is not the charted low water line, see DEPCNT
#           also see LNDARE
# 'RESARE': Restricted area (other objects have an attribute RESTRN, e.g. 'CBLARE'
# 'DEPCNT' # depth contour features, VALDCO = 0 = charted low water line, VALDCO < 0 = drying land
# 'SBDARE' # Seabed area features (includes reefs, coral reefs = 'NATSUR' = 14)
# 'SOUNDG' # Sounding, negative values are drying heights, this is a multipoint feature
# 'DEPARE' # Depth Area, Group 1, DRVAL1 = drying height value for a range of drying values the shoalest is used
# 'UWTROC' # Underwater rock
# 'LNDARE' # Land area: Group 1 (Point, Line and Polygon geometry)
# 'LNDELV' # Land elevation, spot heights and also represented in line geometry
# 'UNSARE' # Unsurveyed Area: Group 1
# 'BUISGL' # Building Single: light houses and other buildings.
# 'BCNISD', 'BCNLAT', 'BCNSAW', 'BCNSPP'  # Beacon features

# If True then all the available feature types are extracted as identified from the ENC source data
# If False then a manually adjusted list is used.
# TODO: User to set this to true if you would like to extract all the features that are present in the collection of
# TODO: s57 files that are being processed. If false then the featureToExtractList is used instead. The latter has been
# TODO: tested and is more likely to work.
extractAlls57FeaturesInData = True

encList = chartGetter(parentFolder)

if extractAlls57FeaturesInData:
    featureToExtractList = featureTypeGetter(encList)
else:
    # Manual setting of features to extract
    # Priority 'Skin of the Earth' features for charting (Group 1) are:
    # 'DEPARE', 'DRGARE', 'FLODOC', 'HULKES', 'LNDARE', 'PONTON', 'UNSARE'
    # featureToExtractList = ['CBLSUB', 'COALNE', 'RESARE', 'DEPCNT', 'SBDARE', 'SOUNDG', 'DEPARE', 'LNDARE', 'LNDELV',
    #                         'UNSARE', "BUISGL", 'UWTROC', 'BCNCAR', 'BCNISD', 'BCNLAT', 'BCNSAW', 'BCNSPP', 'CBLARE',
    #                         'PIPSOL', 'PIPARE']
    featureToExtractList = ['SOUNDG', 'LNDARE', 'LNDELV']

print('Feature type list:')
for f in featureToExtractList:
    print(f'\t{f}')


# List of geometry type to consider for each feature type as some features, e.g. LNDARE, which would be assumed to
# be polygons have alternative representations, i.e. points, due to generalisation at small scale representation.
featureTypeList = ['MULTIPOINT', 'POLYGON', 'POINT', 'LINESTRING']


# SAFEMODE: used to only transfer the fields in the fieldsToRetain list and none of the other fields in the source data.
# This is used when errors occur relating to the field types, e.g. string list or integer list field types
#  that are not supported in shapefiles.
safemode = False
# Set the fields to retain
fieldsToRetain = ['RCID', 'PRIM', 'GRUP', 'OBJL', 'RVER', 'AGEN', 'FIDN', 'FIDS', 'LNAM', 'WATLEV',
                  'OBJNAM']  # 'NATSUR', # StringList type fields cause th memLayer to crash

dateTimeNow = f"_{datetime.datetime.now().strftime('%d_%m_%Y_%Hh%Mm%Ss')}"

# Create folder to store coastline extracts with a date time stamp
folderDateTime = dateTimeNow
extractRoot = os.path.join(os.path.split(parentFolder)[0],
                         f'{os.path.split(parentFolder)[1]}_extracted_{folderDateTime}')

# Make the root directory
os.makedirs(extractRoot)

# Establish the log file
logfile = os.path.join(extractRoot, rf'featureExtraction_logfile_{folderDateTime}.log')
print(f'Logfile in: {logfile}')

log.basicConfig(filename=logfile,
                    level=log.DEBUG,
                    filemode='w',# 'w' = overwrite log file, 'a' = append
                    format='%(asctime)s,   Line:%(lineno)d %(levelname)s: %(message)s',
                    datefmt='%a %d/%b/%Y %I:%M:%S %p')
# Log the path and name of the script used to the logfile
log.info('Script started: ' + sys.argv[0])
# Log the parent folder to the logfile
log.info('Parent folder to find s57 data within: ' + parentFolder)

# Save the script to the outFolder to store with the outputs
shutil.copy2(sys.argv[0], extractRoot)

# Copy the example QGIS project which includes example S.57 data, ENC/chart webservices and the ESRI World Image
# basemap to the output data folder. Users can then trace the source to feature/geometry type extractions including the
# chart specific and global compilations.
if os.path.exists(os.path.join(os.path.split(extractRoot)[0], 'qgis')):
    print(f'Copying QGIS folder: {os.path.join(os.path.split(extractRoot)[0],"qgis")}')
    print(f'To {os.path.join(extractRoot, "qgis")}')
    shutil.copytree(os.path.join(os.path.split(extractRoot)[0], 'qgis'), os.path.join(extractRoot, 'qgis'))
    log.info(f'Copied example QGIS project to: {extractRoot}\qgis')
else:
    log.info(f'Copy failed, QGIS project example does not exist')


# Attempt to save the s57 reference docs to the outfolder
refList = [r'https://iho.int/iho_pubs/standard/S-57Ed3.1/S-57%20Appendix%20B.1%20Annex%20A%20UOC%20Edition%204.1.0_Jan18_EN.pdf',
           r'https://www.hydro.gov.au/prodserv/important-info/SPEC_05_55_AA34159_AUOC.pdf']
for url in refList:
    if not os.path.exists(os.path.join(extractRoot, os.path.split(url)[1])):
        try:
            print(f'Attempting to save to: {os.path.join(extractRoot, os.path.split(url)[1])}')
            urllib.request.urlretrieve(url, os.path.join(extractRoot, os.path.split(url)[1]))
        except:
            print(f'\tCould not download/save: {url}')
    else:
        print('\tFile exists, not overwritten')

#os.path.join(os.path.split(workspace)[0],r'logfile.log')

if extractAlls57FeaturesInData:
    log.info('All available feature types being extracted from the s.57 source data')
noneTypeGeometry = []

for featureToExtract in featureToExtractList:
    print(f'\n**********************************************\nExtracting feature: {featureToExtract}'
          f'\n**********************************************\n')
    for featureType in featureTypeList:
        if featureType == 'LINESTRING':
            geomType = ogr.wkbLineString
        elif featureType == 'POLYGON':
            geomType = ogr.wkbPolygon
        elif featureType == 'POINT':
            geomType = ogr.wkbPoint25D
        elif featureType == 'MULTIPOINT':
            geomType = ogr.wkbMultiPoint25D
        else:
            sys.exit(f'Feature type not handled: {featureType}')

        outFolder = os.path.join(extractRoot, f'{featureToExtract}', f'{featureType}')
        chartExtractFolder = os.path.join(outFolder, f'ENCsContaining{featureType}')
        print(f'Extracting {featureToExtract} of geometry type {featureType} to {outFolder} with chart extracts in'
                 f' {chartExtractFolder}')
        log.info(f'Extracting {featureToExtract} of geometry type {featureType} to {outFolder} with chart extracts in'
                 f' {chartExtractFolder}')

        os.makedirs(outFolder)
        os.makedirs(chartExtractFolder)

        # Flag that sets to True once the memory layer is used. User not required to change this.
        memLayersUsed = False

        s57Driver = ogr.GetDriverByName("S57")

        # AttributesOfListType = []
        failS57SourceList = []

        # Initiate empty lists to contain the path to s57 files that contain or
        # don't contain coastline data. Only used to report on numbers of charts with
        # coastline at the end of the script.
        chartList = []
        chartsNoFeatureList = []
        chartsWithFeatureList = []
        # Create a list to store the shapefiles created for each chart to combine later
        # into a single composite
        chartShapefileList = []

        for enc in encList:
            AttributesOfListType = []
            chartPath = enc
            f = os.path.split(enc)[1]
            if verbose:
                print(f'Chartpath: {chartPath}')
            chartList.append(chartPath)
            # Use the s57 driver to open the chart
            data = s57Driver.Open(chartPath)

            # Get the S57 layer that corresponds to the "featureToExtract" value
            layer = data.GetLayerByName(featureToExtract)
            if layer:
                chartsWithFeatureList.append(chartPath)
                if verbose:
                    print(f'layer: {layer}')
                featureCount = layer.GetFeatureCount()
                if verbose:
                    print(f"Number of features {featureCount}")
                    print(f'layer type: {type(layer)}')
                importFeatureCount = 0
                for feat in layer:
                    geom = feat.GetGeometryRef()
                    if verbose:
                        print(f'\tGeometry (type: {type(geom)}): {geom}')
                        print(f'\tFeatureType: {featureType}')
                        print(f'Feature types match: {featureType==layer.GetGeomType}')
                    try:
                        if feat.geometry().GetGeometryName() != featureType:
                            if verbose:
                                print(f'Layer of same feature name but not matching geometry type: '
                                      f'{featureType} != {feat.geometry().GetGeometryName()}')
                            continue

                    except:
                        log.info(f'{featureToExtract} has a None type geometry')
                        if verbose:
                            print(f'{featureToExtract} has a None type geometry')
                        noneTypeGeometry.append(featureToExtract)
                        continue

                    else:
                        if verbose:
                            print(f'Layer of same feature name and matching geometry type: '
                                  f'{featureType} != '
                                f'{feat.geometry().GetGeometryName()}')
                        importFeatureCount += 1
                        # sys.exit()


            # If the featureToExtract layer does not exist...
            if not layer or importFeatureCount == 0:
                chartsNoFeatureList.append(chartPath)
                print(f'\t\t{featureToExtract} layer in chart not found')
                log.info(f'chart {f} does not contain {featureToExtract}')
                # sys.exit('ERROR: can not find layer in chart')
            # If the coastline layer does exist.
            else:
                print(f'\t\tFound {featureToExtract} layer in chart')
                log.info(f'Chart {f} does contain {featureToExtract}')

                # Get the metadata relating to the ENC collection
                ENCmetaDict = getENCMetadata(data)

                # Get the Coordinate Reference System (CRS) of the layer
                proj = layer.GetSpatialRef()
                if verbose:
                    print(f'\t\t\t\tGet projection: {proj}')
                if verbose:
                    print('\t\t\t\t\nCreate layer in memory')

                # Create an output datasource in memory to initially store
                # the data and convert the field definition to a field
                # that can be exported to a shapefile.
                memDriver = ogr.GetDriverByName("MEMORY")

                # Create a layer in the memory datasource and define attribute
                # table schema along with the CRS.
                memDS = memDriver.CreateDataSource('memData')
                memLayer = memDS.CreateLayer(f, proj, geom_type=geomType)

                # print the ENC layer attribute table schema
                if verbose:
                    print('\n\tS57 ENC schema:')
                if verbose:
                    for field in layer.schema:
                        print(f'\t\t{field.name} (type: {field.GetFieldTypeName(field.GetType())})')
                # Create the attribute table (fields) according to the layer
                # schema.
                memLayer.CreateFields(layer.schema)
                if verbose:
                    print('\nMemLayer fields prior to alteration:')
                    for field in memLayer.schema:
                        print(f'\t\t{field.name} (type: {field.GetFieldTypeName(field.GetType())})')

                indexCounter = 0
                fieldIndexList = []
                if safemode:
                    for field in memLayer.schema:
                        if field.name not in fieldsToRetain:
                            if verbose:
                                print(f'Deleting field: {field.name} at index {indexCounter}')
                            fieldIndexList.append(indexCounter)
                            memLayer.DeleteField(indexCounter)
                        else:
                            indexCounter += 1

                if verbose:
                    print('\nMemLayer fields post alteration due to safemode:')
                for field in memLayer.schema:
                    if verbose:
                        print(f'\t\t{field.name} (type: {field.GetFieldTypeName(field.GetType())})')
                    if field.GetFieldTypeName(field.GetType()) in ['StringList', 'IntegerList']:
                        i = memLayer.GetLayerDefn().GetFieldIndex(field.name)
                        fld_defn = ogr.FieldDefn(field.name, ogr.OFTString)
                        memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_TYPE_FLAG)
                        if verbose:
                            print(f'\t\t\ttype changed to: {field.GetFieldTypeName(field.GetType())})')

                # type to string within the in-memory layer
                if verbose and not safemode:
                    print('\n\tAltering "STATUS" field definition of string list and '
                          'integer list field types to string field type:')

                # Alter the status field type for the in memory layer prior to adding data
                # The 'STATUS' field appears to cause issues if this field type alteration is completed
                # following the addition of data for some submarine cables feature layers.
                for attribute in ['STATUS']:
                    if verbose:
                        print(f'\t\t{attribute}')
                    i = memLayer.GetLayerDefn().GetFieldIndex(attribute)
                    # Alter the field definition only where the field exists in the schema, i.e. not = -1
                    if i != -1:
                        fld_defn = ogr.FieldDefn(attribute, ogr.OFTString)
                        memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_TYPE_FLAG)
                    else:
                        if verbose:
                            print('\t\t\tSTATUS field not found')

                # Add string type fields to contain the source chart file name
                strFields = ["ENCSource", "ENCissDate", "ENCComment"]
                if verbose:
                    print(f'\n\tAdding ENC metadata string type fields to layer: {strFields}')

                for field in strFields:
                    idField = ogr.FieldDefn(field, ogr.OFTString)
                    memLayer.CreateField(idField)

                # Add integer type fields to contain the source chart file name
                intFields = ["ENCScale"]
                if verbose:
                    print(f'\n\tAdding ENC metadata integer type fields to layer: {intFields}')
                for field in intFields:
                    idField = ogr.FieldDefn(field, ogr.OFTInteger)
                    memLayer.CreateField(idField)

                if verbose:
                    print('\n\tS57 memLayer schema post safemode alterations and metadata field additions:')
                count = 0
                for field in memLayer.schema:
                    if field in strFields or field in intFields:
                        continue
                    if verbose:
                        # print(f'Field count: {count}')
                        print(f'\t\t{field.name} (type: {field.GetFieldTypeName(field.GetType())})')

                    layerDefinition = layer.GetLayerDefn()
                    # fieldType = memLayer.GetFieldDefn(count).GetFieldTypeName(fieldTypeCode)
                    # print(f'\t\t\t\tField type code: {fieldType}')
                    # if 'List' in str(fieldType):
                    #     if verbose:
                    #         print(f'\t\tString field type')
                    #     i = memLayer.GetLayerDefn().GetFieldIndex(count)
                    #     fld_defn = ogr.FieldDefn(field.name, ogr.OFTString)
                    #     memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_TYPE_FLAG)
                    count += 1

                # sys.exit()
                # mem_defn = memLayer.GetLayerDefn()
                # if verbose:
                #     print('\t\t\t\tmem_defn complete')
                # sys.exit()

                if f not in [r'test']:

                    if verbose:
                        print('\nGet memory layer definition...')
                    mem_feat = ogr.Feature(memLayer.GetLayerDefn())

                    if verbose:
                        print('\tmem_feat complete')
                        # print("Name  -  Type  Width  Precision")
                        # print(f'Field count: {mem_feat.GetFieldCount()}')
                        # print(f'Field count: {mem_feat.GetFieldCount()}')
                        # for i in range(mem_feat.GetFieldCount()):
                        #     print(i)
                        #     print(mem_feat.GetFieldDefn(i).GetName())
                        #     fieldName = mem_feat.GetFieldDefn(i).GetName()
                        #     fieldTypeCode = mem_feat.GetFieldDefn(i).GetType()
                        #     fieldType = mem_feat.GetFieldDefn(i).GetFieldTypeName(fieldTypeCode)
                        #     fieldWidth = mem_feat.GetFieldDefn(i).GetWidth()
                        #     GetPrecision = mem_feat.GetFieldDefn(i).GetPrecision()
                        #
                        #     print(f'{fieldName} - {fieldType}  - {fieldWidth} -  {GetPrecision}')
                        #     sys.exit()
                    if verbose:
                        print('\t\t\t\tWriting from S57 to in memory layer')
                    featureCount = 1
                    # For each feature in the s57 source layer, transfer the geometry and field values
                    for feature in layer:
                        if verbose:
                            print(f'\t\t\t\t\tcreating feature: {featureCount}')
                        if feature.geometry().GetGeometryName() != featureType:
                            if verbose:
                                print(f'Layer of same name but not matching geometry type: {feature.geometry().GetGeometryName()}')
                            continue
                        # print('Setting feature geometry')
                        # print(f'\tFeature geometry: {feature.geometry}')
                        # Transfer the geometry of the s57 source feature
                        geom = feature.geometry()
                        if verbose:
                            print(f'Iteration on field geometry type: {featureType}')
                            print(f'Feature geometry: {geom}')
                            print(f'X value: {feature.GetGeometryRef().GetX()}')
                            print(f'Y value: {feature.GetGeometryRef().GetY()}')
                            print(f'GetGeomName: {feature.geometry().GetGeometryName()}')
                            print(f'Iteration geometry match feature geometry: {featureType == feature.geometry().GetGeometryName()}')
                        mem_feat.SetGeometry(geom)
                        layerDefinition = layer.GetLayerDefn()
                        if verbose:
                            print(f'\t\tUpdating attribute values of in memory field from s57 source for feature: {featureCount}:')
                        for i in range(feature.GetFieldCount()):
                            if verbose:
                                print(f'\t\t\ti: {i}')
                            fieldName = layerDefinition.GetFieldDefn(i).GetName()
                            if fieldName in strFields or fieldName in intFields:
                                continue
                            fieldTypeCode = layerDefinition.GetFieldDefn(i).GetType()
                            fieldType = layerDefinition.GetFieldDefn(i).GetFieldTypeName(fieldTypeCode)
                            fieldWidth = layerDefinition.GetFieldDefn(i).GetWidth()
                            GetPrecision = layerDefinition.GetFieldDefn(i).GetPrecision()
                            # Field definition
                            if verbose:
                                print(f"\t\t\t\tField: {fieldName}, type: {fieldType}, width: {str(fieldWidth)}, precision: {str(GetPrecision)}")
                            value = feature.GetField(i)
                            if verbose:
                                try:
                                    print(f'\t\t\t\tSetting field {layer.schema[i].name} to {value}')
                                except:
                                    print(
                                        f'\t\t\t\tSetting field {layer.schema[i].name} to {value.encode("utf-8", "replace").decode()}')
                            # SCAMAX and SCAMIN correspond to feature level scale max and min
                            # if layer.schema[i].name in ['SCAMAX', 'SCAMIN'] and value != None:
                            #     log.info(f'{layer.schema[i].name} = {value}')
                            # Get the index for the memLayer field of the same field name. If the schema does not
                            #  match then assuming they are in the same order and have the same fields is inaccurate
                            memLayerLyr_defn = memLayer.GetLayerDefn()
                            i = memLayerLyr_defn.GetFieldIndex(fieldName)
                            if i == -1:
                                if verbose:
                                    print(f'field {fieldName} does not exist in memLayer')
                                continue
                            if verbose:
                                print(f'\t\t\t\t\tIndex in memLayer for {fieldName}: {i}')
                            # sys.exit()

                            if 'List' in str(fieldType):
                                if verbose:
                                    print(f"\t\t\t\t\t\tStringList field type found ({layer.schema[i].name})")
                                if str(fieldName) not in AttributesOfListType:
                                    if verbose:
                                        print(f'\n\t\t\tAttributesOfTypeList: {AttributesOfListType}')
                                    AttributesOfListType.append(str(fieldName))
                                if value is not None:
                                    if verbose:
                                        print(f'\t\t\t\t\tConverting list field ({layer.schema[i].name}) content ({value}) to comma separated string')
                                        # print(f'\t\t\t\tField content type: {type(value)}')
                                    # Convert to a string with values separated by a comma where there are more than one values
                                    mem_feat.SetField(i, ",".join([str(i) for i in value]))

                                    # print(",".join(value))
                                    # sys.exit('Exiting on join value...')
                                else:
                                    # Setfield can take the index for the field or the field name
                                    mem_feat.SetField(fieldName, value)
                            else:
                                try:
                                    mem_feat.SetField(fieldName, value)
                                except:
                                    mem_feat.SetField(fieldName, f'{value.encode("utf-8", "replace").decode()}')
                        # if verbose:
                        #     print('ENCmetaDict:')
                        #     for k, v in ENCmetaDict.items():
                        #         print(f'\tkey: {k}')
                        #         print(f'\tvalue: {v}')
                        #         print(f'\tvalue type: {type(v)}')
                        #         print(f'\tkey: {k}, value: {v}, value type: {type(v)}')

                        metaDict = {"ENCSource":"name", "ENCissDate":"issueDate", "ENCComment":"comment", "ENCScale":"scale"}

                        if verbose:
                            print('\nUpdate field values from DSID source:')
                        for k, v in metaDict.items():
                            try:
                                i = memLayer.GetLayerDefn().GetFieldIndex(k)
                                if verbose:
                                    print(f'\t{k} field at index {i} being updated to: {str(ENCmetaDict[v])}')
                                mem_feat.SetField(i, str(ENCmetaDict[v]))
                            except:
                                mem_feat.SetField(i, 'Transfer from s57 failed')

                        if verbose:
                            print('\t\t\tSaving memLayer')
                        memLayer.CreateFeature(mem_feat)
                        featureCount += 1

                        # mem_feat.Destroy() # Destroy the feature to free resources

                    # memDS.Destroy # Free memory
                    # For string list and integer list field types, redefine field
                    # type to string within the in-memory layer
                    if verbose:
                        print('\n\tAltering field definition of string list and '
                              'integer list field types to string field type:')
                    for a in AttributesOfListType:
                        if verbose:
                            print(f'\t\t{a}')
                        i = memLayer.GetLayerDefn().GetFieldIndex(a)
                        fld_defn = ogr.FieldDefn(a, ogr.OFTString)
                        memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_TYPE_FLAG)

                    if verbose:
                        print('\n\tmemLayer schema post StringList to String type conversion:')
                    for field in memLayer.schema:
                        if verbose:
                            print(f'\t\t{field.name} type: {field.GetFieldTypeName(field.GetType())}')
                        # if field.name == "LNAM_REFS" or field.name == "FFPT_RIND":
                        #     print('Can alter field from here??')


                    if verbose:
                        print('\n\tWriting from memory to shapefile')
                    # Create the output shapefile
                    # Create a new Shapefile
                    print(f'chartExtractFolder: {chartExtractFolder}')
                    print(f'f: {f}')
                    outSHP = os.path.join(chartExtractFolder, f"{f}.shp")
                    print(f'outShp: {outSHP}')
                    # Append output shapefile to the list to use it later to
                    # combine all shapefiles into a global shapefile
                    chartShapefileList.append(outSHP)
                    shpDriver = ogr.GetDriverByName("ESRI Shapefile")
                    shpDS = shpDriver.CreateDataSource(outSHP)
                    # Create line layer to match the CRS of the source data
                    shpLayer = shpDS.CreateLayer(f, proj, geom_type=geomType)
                    # Create the attribute table to match the in memory schema
                    if verbose:
                        print('Creating shapefile schema...')
                    shpLayer.CreateFields(memLayer.schema)
                    shp_defn = shpLayer.GetLayerDefn()
                    shp_feat = ogr.Feature(shp_defn)
                    # if verbose:
                    #     print('Copy the features, feature by feature, to shapefile')
                    counter = 1
                    for feature in memLayer:
                        if verbose:
                            print(f'\t\tProcessing feature: {counter}')
                        counter += 1
                        geom = feature.geometry()
                        shp_feat.SetGeometry(geom)
                        for i in range(feature.GetFieldCount()):
                            value = feature.GetField(i)
                            # if verbose:
                            #     print(f'\t\tSetting field {memLayer.schema[i].name} to {value}')
                            shp_feat.SetField(i, value)

                        shpLayer.CreateFeature(shp_feat)

                    # Save the changes to the shapefile
                    shpDS.SyncToDisk()
                    # sys.exit()

                    memLayersUsed = True
                    # print(f'AttributeOfListType list: {AttributesOfListType}')
                    # Reset the list as not all ENC files have the same table structure
                    # TODO: may need to check that all schema definitions are the same
                    #       prior to combining into a global dataset?
                    AttributesOfListType = []
                    # print(f'AttributeOfListType list: {AttributesOfListType}')
                    # sys.exit('Exiting to understand processing')
                else:
                    failS57SourceList.append(f)
                    log.error('{f} failed to be converted but contains {featureToExtract}')

        log.info('Shapefile conversion for each s57 chart complete')
        # Convert all the individual ENC shapefiles into one shapefile
        print('\nCombining all ENC shapefiles to a global shapefile')
        # If there are no shapefiles generated from charts for the feature/feature type combination then delete the
        # folder for this combination and move on.
        if len(chartList) == 0:
            sys.exit(f'No ENC files were found, exiting...')
        if len(chartShapefileList) == 0:
            print('No feature/geometry type combinations were found, deleting folder...')
            shutil.rmtree(outFolder)
            continue

        globalShp = os.path.join(outFolder, f"global_{featureToExtract}_{featureType}.shp")
        if verbose:
            print(f'\t{globalShp}')
            log.info(f'globalShp: {globalShp}')
        shpDS = shpDriver.CreateDataSource(globalShp)
        # Create line layer to match the CRS of the source data
        # Create spatial reference
        if verbose:
            print('\tSetting the CRS')
            log.info('Setting the CRS')
        proj = osr.SpatialReference()
        proj.ImportFromEPSG(4326)

        globalShpLayer = shpDS.CreateLayer('global', proj, geom_type=geomType)
        if verbose:
            print('\tCreated the global shape layer')
            log.info('Created the global shape layer')
        # Create the attribute table to match the in memory schema
        globalShpLayer.CreateFields(memLayer.schema)
        if verbose:
            print('\tCreated the schema in the global shapefile')
            log.info('Created the schema in the global shapefile')
        globalShp_defn = globalShpLayer.GetLayerDefn()
        if verbose:
            print('\tCreating the shp_feature')
            log.info('Creating the shp_feature')
        shp_feat = ogr.Feature(globalShp_defn)
        # Process each chart coastline shapefile
        for shpFile in chartShapefileList:
            # print(f'Processing: {os.path.split(shpFile)[1]}')
            if verbose:
                print(f'\tProcessing: {shpFile}')
            ds = ogr.Open(shpFile)
            lyr = ds.GetLayer()
            for feat in lyr:
                out_feat = ogr.Feature(globalShpLayer.GetLayerDefn())
                out_feat.SetGeometry(feat.GetGeometryRef().Clone())
                for i in range(feat.GetFieldCount()):
                    value = feat.GetField(i)
                    # if verbose:
                    #     print(f'\t\tSetting field {lyr.schema[i].name} to {value}')
                    out_feat.SetField(i, value)
                globalShpLayer.CreateFeature(out_feat)
                globalShpLayer.SyncToDisk()

        log.info(f'Composite shapefile complete: {globalShp}')
        print(f'\noutFolder for global shape file: {outFolder}')
        print('\tComposite complete.')

        print(f'\n{len(chartsWithFeatureList) + len(chartsNoFeatureList)} charts found')
        print(f'\t{len(chartsWithFeatureList)} charts found which contain {featureToExtract} features')
        print(f'\t{len(chartsNoFeatureList)} charts with no {featureToExtract} features')
        for g in failS57SourceList:
            print(g)
            log.error('Failed to convert {featureToExtract} in {g}')

        print(f'\nScript completed in {round((time.time() - t0)/60, 2)} minutes')

        log.info(f'{len(chartsWithFeatureList) + len(chartsNoFeatureList)} charts found')
        log.info(f'{len(chartsWithFeatureList)} charts found which contain {featureToExtract} features')
        log.info(f'{len(chartsNoFeatureList)} charts with no {featureToExtract} layer')
        log.info(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')

print(f'\nNone type geometry for the following s57 feature types:')
noneTypeGeometrySet = set(noneTypeGeometry)
for noneType in noneTypeGeometrySet:
    print(f'\t{noneType}')
    log.info(f'{noneType} s57 feature failed extraction due to a noneType geometry')

log.info(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')
print(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')

