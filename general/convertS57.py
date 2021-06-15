###############################################################################
# Aim: Find ENC s57 data (.000 files), extract the feature of interest into a shapefile
#      and attribute as per the source schema and add metadata from the s57 dataset
#      including ENC name, ENC issue date, ENC comment and ENC scale.
#
# An in memory layer is used between the source s57 data and the shapefile
# to enable transforming fields in the s57 data that are not supported
# in shapefiles (integer list and string list field types). These fields
# are converted to string field types and the content of the field is 
# converted to a comma seprated string.
#
# Each input chart containing a coastline results in a shapefile. The shapefiles
# are then combined into a composite shapefile.
#
# A folder is created at the same level as the input parent folder from which the scipt starts searching for .000 files.
# The folder contains the national shapefile, the Python script, a log file and a subfolder of the invidividual
# shapefiles, one for each input .000 file that contains the feature of interest.
# Useful open source Python reference https://livebook.manning.com/book/geoprocessing-with-python/chapter-3/126
#
# For S57 feature types see: https://iho.int/iho_pubs/standard/S-57Ed3.1/S-57%20Appendix%20B.1%20Annex%20A%20UOC%20Edition%204.1.0_Jan18_EN.pdf
#
# Duncan Moore, 5 May 2021
###############################################################################

# Import required libraries
from osgeo import ogr
import os
import sys
import datetime
import time
import shutil
import logging as log


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
        print(f'\nENC: {dsnm}, Issue date: {issueDate}, Scale: 1:{scale}, comment: {comment}')
    return({'name':dsnm,'issueDate':issueDate,'scale':scale,'comment':comment})

# Set intial time
t0 = time.time()

# parentFolder from which all content within subfolders is searched for s57 data
parentFolder = input("Enter the top folder to search within for s57 (.000) data: ")
while not os.path.exists(f'{parentFolder}'):# Test to make sure an input was provided
    print('No existing top folder provided...')
    parentFolder = input("\tEnter the top folder: ")

# Make True/False depending on whether you want to see all the print statements
verbose = False

# S57 feature type to extract
featureToExtract = 'CBLSUB'
# featureToExtract = 'COALNE'
# TODO: user input for featureToExtract does not seem to work, investigate.
# featureToExtract = parentFolder = input("Enter the s57 feature type (e.g. 'CBLSUB' = submarine cables, 'COALNE' = coastline): ")
# print(f'feature type to extract: {featureToExtract}, feature type: {type(featureToExtract)}')
# sys.exit()
# TODO: extract features from an attribute selection on 'DEPCNT' feature type
#       This requires an second attribute query within this layer
# featureToExtract = 'DEPCNT'

# TODO: get the geometry type from an input feature rather then hard coding
# to a linestring, this will fail if extracting a point feature unless it is
# changed by the user to the correct geometry type
geomType = ogr.wkbLineString

# Create folder to store coastline extracts with a date time stamp
folderDateTime = f"_{datetime.datetime.now().strftime('%d_%m_%Y_%Hh%Mm%Ss')}"
outFolder = os.path.join(os.path.split(parentFolder)[0], 
                         f'{os.path.split(parentFolder)[1]}_extracted_{featureToExtract}_{folderDateTime}')
chartExtractFolder = os.path.join(outFolder, featureToExtract)

os.mkdir(outFolder)
os.mkdir(chartExtractFolder)
# Save the script to the outFolder to store with the outputs
shutil.copy2(sys.argv[0], outFolder)

# Establish the log file
logfile = os.path.join(outFolder, rf'extract_{featureToExtract}_logfile_{folderDateTime}.log')
print(f'Logfile in: {logfile}')

#os.path.join(os.path.split(workspace)[0],r'logfile.log')
log.basicConfig(filename=logfile,
                    level=log.DEBUG,
                    filemode='w',# 'w' = overwrite log file, 'a' = append
                    format='%(asctime)s,   Line:%(lineno)d %(levelname)s: %(message)s',
                    datefmt='%a %d/%b/%Y %I:%M:%S %p')
# Log the path and name of the script used to the logfile
log.info('Script started: ' + sys.argv[0])
# Log the parent folder to the logfile
log.info('Parent folder to find s57 data within: ' + parentFolder)

# Flag that sets to True once the memory layer is used
memLayersUsed = False

s57Driver = ogr.GetDriverByName("S57")

# AttributesOfListType = []
failS57SourceList = []

# Initiate empty lists to contain the path to s57 files that contain or
# don't contain coastline data. Only used to report on numbers of charts with
# coastline at the end of the script.
chartList = []
chartsNoFeatureList = []
# Create a list to store the shapefiles created for each chart to combine later 
# into a single composite
chartShapefileList = []


# TODO: Is the S57 driver combining .000 with later files (.001 etc.)
#  i.e. are each of the .000, .001, .002 files processed separately or only the
#  most recent, e.g. .002 in the example above
for root, folder, files in os.walk(parentFolder):
    for f in files:
        # s57 data files end with a '000' extension.
        if f.endswith('000'):
            AttributesOfListType = []
            chartPath = os.path.join(root, f)
            print(f'Chartpath: {chartPath}')
            chartList.append(chartPath)
            # Use the s57 driver to open the chart
            data = s57Driver.Open(chartPath)
            
            # Get the S57 layer that corresponds to the "featureToExtract" value
            layer = data.GetLayerByName(featureToExtract)
            # If the featureToExtract layer does not exist...
            if not layer:
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
                
                
                # if memLayersUsed:
                #     # Delete variables from memory
                #     # del memDS
                #     # del memDriver
                #     # del memLayer
                #     mem_feat.Destroy() # Destroy the feature to free resources
                #     memDriver.Destroy()
                #     memDS.Destroy() # Free memory
                #     memLayer.Destroy()
                
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
                for field in layer.schema:
                    if verbose:
                        print(f'\t\t{field.name} type: {field.GetFieldTypeName(field.GetType())}')
                # Create the attribute table (fields) according to the layer
                # schema.
                memLayer.CreateFields(layer.schema)
                # For string list and integer list field types, redefine field 
                # type to string within the in-memory layer
                if verbose:
                    print('''\n\tAltering field definition of string list and
                          integer list field types to string field type:''')

                # Alter the status field type for the in memory layer prior to adding data
                # The 'STATUS' field appears to cause issues if this field type alteration is completed
                # following the addition of data for some submarine cables feature layers.

                for a in ['STATUS']:
                    if verbose:
                        print(f'\t\t{a}')
                    i = memLayer.GetLayerDefn().GetFieldIndex(a)
                    # Alter the field definition only where the field exists in the schema, i.e. not = -1
                    if i != -1:
                        fld_defn = ogr.FieldDefn(a, ogr.OFTString)
                        memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_ALL_FLAG)
                    else:
                        if verbose:
                            print('STATUS field not found')
                if verbose:
                    print('\t\t\t\tAdding ENC metadata fields to layer')
                # Add string type fields to contain the source chart file name
                strFields = ["ENCSource", "ENCissDate", "ENCComment"]

                for field in strFields:
                    idField = ogr.FieldDefn(field, ogr.OFTString)
                    memLayer.CreateField(idField)
                
                # Add integer type fields to contain the source chart file name
                intFields = ["ENCScale"]
                for field in intFields:
                    idField = ogr.FieldDefn(field, ogr.OFTInteger)
                    memLayer.CreateField(idField)
                
                if verbose:
                    print('\n\tS57 memLayer schema:')
                count = 0
                for field in memLayer.schema:
                    if verbose:
                        print(f'Field count: {count}')
                        print(f'\t\t{field.name} type: {field.GetFieldTypeName(field.GetType())}')
                        count += 1
                # sys.exit()
                # mem_defn = memLayer.GetLayerDefn()
                # if verbose:
                #     print('\t\t\t\tmem_defn complete')
                if f not in [r'test']:
                    
                    if verbose:
                        print('\t\t\t\tGet layer definition...')
                    mem_feat = ogr.Feature(memLayer.GetLayerDefn())
                    if verbose:
                        print('\t\t\t\tmem_feat complete')
                    if verbose:
                        print('\t\t\t\tWriting from S57 to in memory layer')
                    featureCount = 1
                    # For each feature in the s57 source layer, transfer the geometry and field values
                    for feature in layer:
                        if verbose:
                            print(f'\t\t\t\t\tcreating feature: {featureCount}')
                        # print('Setting feature geometry')
                        # print(f'\tFeature geometry: {feature.geometry}')
                        # Transfer the geometry of the s57 source feature
                        geom = feature.geometry()
                        mem_feat.SetGeometry(geom)
                        layerDefinition = layer.GetLayerDefn()
                        if verbose:
                            print(f'\t\tUpdating attribute values of in memory field from s57 source for feature: {featureCount}:')
                        for i in range(feature.GetFieldCount()):
                            if verbose:
                                print(f'i: {i}')
                            fieldName = layerDefinition.GetFieldDefn(i).GetName()
                            if fieldName in strFields or fieldName in intFields:
                                continue
                            fieldTypeCode = layerDefinition.GetFieldDefn(i).GetType()
                            fieldType = layerDefinition.GetFieldDefn(i).GetFieldTypeName(fieldTypeCode)
                            fieldWidth = layerDefinition.GetFieldDefn(i).GetWidth()
                            GetPrecision = layerDefinition.GetFieldDefn(i).GetPrecision()
                            # Field definition
                            if verbose:
                                print("\t\t\t" + fieldName + " - " + fieldType + " " + str(fieldWidth) + " " + str(GetPrecision))
                            value = feature.GetField(i)
                            if verbose:
                                print(f'\t\tSetting field {layer.schema[i].name} to {value}')
                            # SCAMAX and SCAMIN correspond to feature level scale max and min
                            # if layer.schema[i].name in ['SCAMAX', 'SCAMIN'] and value != None:
                            #     log.info(f'{layer.schema[i].name} = {value}')
                            if 'List' in str(fieldType):
                                if verbose:
                                    print(f"\t\t\t\t\tList field type found ({layer.schema[i].name})")
                                if str(fieldName) not in AttributesOfListType:
                                    if verbose:
                                        print(f'\n\t\t\tAttributesOfTypeList: {AttributesOfListType}')
                                    AttributesOfListType.append(str(fieldName))
                                if value is not None:
                                    if verbose:
                                        print(f'\t\t\t\t\tConverting list field ({layer.schema[i].name}) content ({value}) to comma separated string')
                                        # print(f'\t\t\t\tField content type: {type(value)}')
                                    mem_feat.SetField(i, ",".join([str(i) for i in value]))
                                        
                                    # print(",".join(value))
                                    # sys.exit('Exiting on join value...')
                                else:
                                    mem_feat.SetField(i, value)
                            else:
                                mem_feat.SetField(i, value)
                        if verbose:
                            print('ENCmetaDict:')
                            for k, v in ENCmetaDict.items():
                                print(f'\tkey: {k}, value: {v}, value type: {type(v)}')

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

                        # mem_feat.Destroy() # Destroy the feature to free resources
                    
                    # memDS.Destroy # Free memory
                    # For string list and integer list field types, redefine field
                    # type to string within the in-memory layer
                    if verbose:
                        print('''\n\tAltering field definition of string list and
                              integer list field types to string field type:''')
                    for a in AttributesOfListType:
                        if verbose:
                            print(f'\t\t{a}')
                        i = memLayer.GetLayerDefn().GetFieldIndex(a)
                        fld_defn = ogr.FieldDefn(a, ogr.OFTString)
                        memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_ALL_FLAG)
                    
                    if verbose:
                        print('\n\tmemLayer schema:')
                    for field in memLayer.schema:
                        if verbose:
                            print(f'\t\t{field.name} type: {field.GetFieldTypeName(field.GetType())}')
                        # if field.name == "LNAM_REFS" or field.name == "FFPT_RIND":
                        #     print('Can alter field from here??')
                    

                    if verbose:
                        print('\n\tWriting from memory to shapefile')
                    # Create the output shapefile
                    # Create a new Shapefile
                    outSHP = os.path.join(chartExtractFolder, f"{f}.shp")
                    # Append output shapefile to the list to use it later to 
                    # combine all shapefiles into a national shapefile
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
                    #       prior to combining into a national dataset?
                    AttributesOfListType = []
                    # print(f'AttributeOfListType list: {AttributesOfListType}')
                    # sys.exit('Exiting to understand processing')
                else:
                    failS57SourceList.append(f)
                    log.error('{f} failed to be converted but contains {featureToExtract}')

log.info('Shapefile conversion for each s57 chart complete')

print('\nCombining all chart coastline shapefiles to a national shapefile')
# Convert all the invidual coastline shapefiles into one shapefile
if len(chartList) == 0:
    sys.exit(f'No ENC files were found to contain {featureToExtract}, exiting...')

nationalShp = os.path.join(outFolder, f"national_{featureToExtract}.shp")
if verbose:
    print(f'\t{nationalShp}')
    log.info(f'nationalShp: {nationalShp}')
shpDS = shpDriver.CreateDataSource(nationalShp)
# Create line layer to match the CRS of the source data
# Create spatial reference
if verbose:
    print('\tSetting the CRS')
    log.info('Setting the CRS')
proj = ogr.osr.SpatialReference()
proj.ImportFromEPSG(4326)

nationalShpLayer = shpDS.CreateLayer('national', proj,geom_type=geomType)
if verbose:
    print('\tCreated the national shape layer')
    log.info('Created the national shape layer')
# Create the attribute table to match the in memory schema
nationalShpLayer.CreateFields(memLayer.schema)
if verbose:
    print('\tCreated the schema in the national shapefile')
    log.info('Created the schema in the national shapefile')
nationalShp_defn = nationalShpLayer.GetLayerDefn()
if verbose:
    print('\tCreating the shp_feature')
    log.info('Creating the shp_feature')
shp_feat = ogr.Feature(nationalShp_defn)
# Process each chart coastline shapefile
for shpFile in chartShapefileList:
    # print(f'Processing: {os.path.split(shpFile)[1]}')
    if verbose:
        print(f'\tProcessing: {shpFile}')
    ds = ogr.Open(shpFile)
    lyr = ds.GetLayer()
    for feat in lyr:
        out_feat = ogr.Feature(nationalShpLayer.GetLayerDefn())
        out_feat.SetGeometry(feat.GetGeometryRef().Clone())
        for i in range(feat.GetFieldCount()):
            value = feat.GetField(i)
            # if verbose:
            #     print(f'\t\tSetting field {lyr.schema[i].name} to {value}')
            out_feat.SetField(i, value)     
        nationalShpLayer.CreateFeature(out_feat)
        nationalShpLayer.SyncToDisk()

log.info(f'Composite shapefile complete: {nationalShp}')
print(f'n\outFolder for national shape file: {outFolder}')
print('\tComposite complete.')
                
print(f'\n{len(chartList)} charts found')
print(f'\t{len(chartsNoFeatureList)} charts with no {featureToExtract} layer')
print(f'S57 source data containing {featureToExtract}:')
for g in failS57SourceList:
    print(g)
    log.error('Failed to convert {featureToExtract} in {g}')
    
print(f'\nScript completed in {round((time.time() - t0)/60, 2)} minutes')

log.info(f'{len(chartList)} charts found')
log.info(f'{len(chartsNoFeatureList)} charts with no {featureToExtract} layer')
log.info(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')

print('Script complete.')

