###############################################################################
# Aim: Find s57 data, extract the coastline into a shapefile and attribute with
#      the source chart file name

# An in memory layer is used between the source s57 data and the shapefile
# to enable transforming three fields in the s57 data that are not supported
# in shapefiles (integer list and string list field types). These fields
# are converted to string field types and the content of the field is 
# converted to a comma seprated string.
#
# Each input chart containing a coastline results in a shapefile. The shapefiles
# are then combined into a composite shapefile.
#
# Useful open source Python reference https://livebook.manning.com/book/geoprocessing-with-python/chapter-3/126
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

# Set intial time
t0 = time.time()

# parentFolder from which all content within subfolders is searched for s57 data
parentFolder = input("Enter the top folder: ")
while not os.path.exists(f'{parentFolder}'):# Test to make sure an input was provided
    print('No existing top folder provided...')
    parentFolder = input("\tEnter the top folder: ")

# Make True/False depending on whether you want to see all the print statements
verbose = False

# Create folder to store coastline extracts with a date time stamp
folderDateTime = f"AHOCoastline_{datetime.datetime.now().strftime('%d_%m_%Y_%Hh%Mm%Ss')}"
outFolder = os.path.join(os.path.split(parentFolder)[0], 
                         f'{os.path.split(parentFolder)[1]}_extracted_{folderDateTime}')
os.mkdir(outFolder)
# Save the script to the outFolder to store with the outputs
shutil.copy2(sys.argv[0], outFolder)

# Establish the log file
logfile = os.path.join(outFolder,r'logfile.log')

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

s57Driver = ogr.GetDriverByName("S57")

# Initiate empty lists to contain the path to s57 files that contain or
# don't contain coastline data. Only used to report on numbers of charts with
# coastline at the end of the script.
chartList = []
chartsNoCoastList = []
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
            print(f'\n{f}')
            chartPath = os.path.join(root, f)
            chartList.append(chartPath)
            # Use the s57 driver to open the chart
            data = s57Driver.Open(chartPath)

            # Get a specific layer
            # Coastline layers have the name "COALNE"
            layer = data.GetLayerByName("COALNE")
            # If the coastline layer does not exist...
            if not layer:
                chartsNoCoastList.append(chartPath)
                print('\t\tCoastline layer in chart not found')
                log.info(f'{f} does not contain coastline')
                # sys.exit('ERROR: can not find layer in chart')
            # If the coastline layer does exist.
            else:
                print('\t\tFound coastline layer in chart')
                log.info(f'{f} does contain coastline')
                # Create an output datasource in memory
                memDriver = ogr.GetDriverByName('MEMORY')
                memDS = memDriver.CreateDataSource('memData')
    
                proj = layer.GetSpatialRef()            
    
                # Create a layer in the memory datasource and define attribute
                # table schema.
                memLayer = memDS.CreateLayer(f, proj,geom_type=ogr.wkbLineString)
                memLayer.CreateFields(layer.schema)
                # # Add a field to contain the source chart file name
                idField = ogr.FieldDefn("sourcChart", ogr.OFTString)
                memLayer.CreateField(idField)
                
                mem_defn = memLayer.GetLayerDefn()
                mem_feat = ogr.Feature(mem_defn)
                if verbose:
                    print('Writing from S57 to in memory layer')
                featureCount = 1
                for feature in layer:
                    if verbose:
                        print(f'creating feature: {featureCount}')
                    featureCount += 1
                    # print('Setting feature geometry')
                    # print(f'\tFeature geometry: {feature.geometry}')
                    geom= feature.geometry()
                    mem_feat.SetGeometry(geom)
                    for i in range(feature.GetFieldCount()):
                        value = feature.GetField(i)
                        if verbose:
                            print(f'\t\tSetting field {layer.schema[i].name} to {value}')
                        if memLayer.schema[i].name in ['LNAM_REFS', 'FFPT_RIND', 'COLOUR'] and value != None:
                            if verbose:
                                print('Converting list field content to comma separated string')
                                print(f'Field content type: {type(value)}')
                            mem_feat.SetField(i, ",".join(value))
                        else:
                            mem_feat.SetField(i, value)
                    mem_feat.SetField("sourcChart", f.split('.')[0])
                    if verbose:
                        print('Saving memLayer')
                    memLayer.CreateFeature(mem_feat)
                
                # Change "LNAM_REFS" StringList field to string and
                # change "FFPT_RIND" IntegerList to Integer
                i = memLayer.GetLayerDefn().GetFieldIndex('LNAM_REFS')
                # print(f'Index of field "LNAM_REFS": {i}')
                fld_defn = ogr.FieldDefn('LNAM_REFS', ogr.OFTString)
                memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_ALL_FLAG)
                
                i = memLayer.GetLayerDefn().GetFieldIndex('FFPT_RIND')
                # print(f'Index of field "FFPT_RIND": {i}')
                fld_defn = ogr.FieldDefn('FFPT_RIND', ogr.OFTString)
                memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_ALL_FLAG)
                
                i = memLayer.GetLayerDefn().GetFieldIndex('COLOUR')
                # print(f'Index of field "COLOUR": {i}')
                fld_defn = ogr.FieldDefn('COLOUR', ogr.OFTString)
                memLayer.AlterFieldDefn(i, fld_defn, ogr.ALTER_ALL_FLAG)
                
                # if verbose:
                #     print('\nmemLayer schema')
                # for field in memLayer.schema:
                #     if verbose:
                #         print(f'\t{field.name} type: {field.GetFieldTypeName(field.GetType())}')
                #     if field.name == "LNAM_REFS" or field.name == "FFPT_RIND":
                #         print('Can alter field from here??')
                        
                # To grab a field name by index
                # print(layer.schema[1].name)
                
                print('\t\tWriting from memory to shapefile')
                # Create the output shapefile
                # Create a new Shapefile
                outSHP = os.path.join(outFolder, f"{f}{datetime.datetime.now().strftime('%d_%m_%Y_%Hh%Mm%Ss')}.shp")
                chartShapefileList.append(outSHP)
                shpDriver = ogr.GetDriverByName("ESRI Shapefile")
                shpDS = shpDriver.CreateDataSource(outSHP)
                # Create line layer to match the CRS of the source data
                shpLayer = shpDS.CreateLayer(f, proj,geom_type=ogr.wkbLineString)
                # Create the attribute table to match the in memory schema
                shpLayer.CreateFields(memLayer.schema)
                shp_defn = shpLayer.GetLayerDefn()
                shp_feat = ogr.Feature(shp_defn)
                if verbose:
                    print('Copy the features, feature by feature, to shapefile')
                counter = 1
                for feature in memLayer:
                    if verbose:
                        print(f'\tProcessing feature: {counter}')
                    counter += 1
                    geom = feature.geometry()
                    shp_feat.SetGeometry(geom)
                    for i in range(feature.GetFieldCount()):
                        value = feature.GetField(i)
                        if verbose:
                            print(f'\t\tSetting field {memLayer.schema[i].name} to {value}')
                        shp_feat.SetField(i, value)                        
                    
                    shpLayer.CreateFeature(shp_feat)

                # Save the changes to the shapefile
                shpDS.SyncToDisk()

log.info(f'Shapefile conversion for each s57 chart complete')

print('\nCombining all chart coastline shapefiles to a national shapefile')
# Convert all the invidual coastline shapefiles into one shapefile
nationalShp = os.path.join(outFolder, "nationalCoastline.shp")
shpDS = shpDriver.CreateDataSource(nationalShp)
# Create line layer to match the CRS of the source data
# Create spatial reference
proj = ogr.osr.SpatialReference()
proj.ImportFromEPSG(4326)
nationalShpLayer = shpDS.CreateLayer('national', proj,geom_type=ogr.wkbLineString)
# Create the attribute table to match the in memory schema
nationalShpLayer.CreateFields(memLayer.schema)
nationalShp_defn = nationalShpLayer.GetLayerDefn()
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
            if verbose:
                print(f'\t\tSetting field {lyr.schema[i].name} to {value}')
            out_feat.SetField(i, value)     
        nationalShpLayer.CreateFeature(out_feat)
        nationalShpLayer.SyncToDisk()

log.info(f'Composite shapefile complete: {nationalShp}')
print('\tComposite complete.')
                
print(f'\n{len(chartList)} charts found')
print(f'\t{len(chartsNoCoastList)} charts with no coastline layer')
print(f'\nScript completed in {round((time.time() - t0)/60, 2)} minutes')

log.info(f'{len(chartList)} charts found')
log.info(f'{len(chartsNoCoastList)} charts with no coastline layer')
log.info(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')

