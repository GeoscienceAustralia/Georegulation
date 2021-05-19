########################################################################################################################
### Build an ESRI mosaic dataset from all imagery found within a parent folder. For each image capture the location of the
### image and, optionally, an SHA256 hash value. The latter to enable later comparison of values across data holdings
### to identify duplicates. Image paths are able to be exported from ESRI mosaic datasets but storing this information
### in the attribute table is more accessible.
###
### Within the user provided parent folder the following sub-folders are not considered for image content: "~snapshot",
### "DEA_Data", "$RECYCLE.BIN".
###
###
###### Duncan Moore. May 2019.
########################################################################################################################

import arcpy
import hashlib
from datetime import datetime
import os
import logging as log
import sys
########################################################################################################################
### Functions
########################################################################################################################

def findRaster(path):
    arcpy.env.workspace = os.path.join(path)

    # Get and print a list of raster files from the workspace
    rasters = arcpy.ListRasters()
    # If no rasters then return to the mainline
    try:
        if len(rasters) == 0:
            print("\tNo rasters found")
            return
    except:
        return
    for raster in rasters:
        if continueProcess in ['Y', 'y'] and os.path.join(path, raster) in processedList:
            print('*** Raster previously added to mosaic dataset or failed import ({})'.format(os.path.join(path, raster)))
            # TODO: Write to log where previous rasters have been processed.
            log.error('{}: previously failed attempt to load into mosaic dataset'.format(os.path.join(path, raster)))
            continue
        print('\nProcessing: {}'.format(os.path.join(path, raster)))
        # print('\tExists: {}'.format(os.path.exists(os.path.join(path, raster))))
        if os.path.join(path, raster) in processed.keys():
            print("\tRaster previously processed")
            # Move to next raster in the list
            continue
        # If the spatial reference is unknown
        try:
            spatial_ref = arcpy.Describe(os.path.join(path, raster)).spatialReference
        except:
            # If no spatial reference then continue to the next iteration
            log.error("{}: no spatial reference".format(os.path.join(path, raster)))
            print('\tNo CRS found')
            continue

        try:
            if spatial_ref.name in ("Unknown", "GCS_Undefined") or spatial_ref.projectionCode == 0:
                log.error("{}: no spatial reference".format(os.path.join(path, raster)))
                print('\t\tCRS \'Unknown\' or \'"GCS_Undefined"')
                continue
        except:
            continue

        # Otherwise, print out the feature class name and
        # spatial reference
        else:
            # print('\tCRS: '.format(arcpy.Describe(os.path.join(path, raster)).spatialReference))
            print("\t\tCRS Name: {}".format(spatial_ref.name))
            print("\t\t{0} : type: {1}".format(raster, spatial_ref.type))
            print("\t\t{0} : PCSCode: {1}".format(raster, spatial_ref.PCSCode))
            print("\t\t{0} : PCSName: {1}".format(raster, spatial_ref.PCSName))
            print("\t\t{0} : Abbreviation: {1}".format(raster, spatial_ref.abbreviation))
            print("\t\t{0} : Projection code: {1}".format(raster, spatial_ref.projectionCode))
            print("\t\t{0} : Projection Name: {1}".format(raster, spatial_ref.projectionName))
            # Load the raster dataset into the raster catalog
            arcpy.env.workspace = path
            try:
                print('\tAdd raster to mosaic...')
                arcpy.AddRastersToMosaicDataset_management(rasterCatalog, "raster dataset", os.path.join(path, raster))
                log.info('raster added to mosaic')
            except:
                print('Add raster to mosaic failed')
                log.error('{}: update cursor failed'.format(os.path.join(path, raster)))
                continue
            #arcpy.RasterToGeodatabase_conversion(raster, rasterCatalog)
            # Update the path to the raster data
            with arcpy.da.UpdateCursor(rasterCatalog, ('path', 'SHA256Hash', 'DataType')) as cursor:
                print('\tupdating raster catalog table...')
                for row in cursor:
                    # print(row)
                    # print(len(row))
                    if row[0] is None:
                        row[0] = os.path.join(path, raster)
                        # Calc hash if hashCalc = True, script is faster without hash calculation to process
                        if hashCalc:
                            row[1] = hash(os.path.join(path, raster))
                        # '\DATA' prefixes a data type folder name and this can be used to tag the data type
                        if '{0}DATA{0}'.format(os.sep) in path:
                            row[2] = path.split(os.sep)[path.split(os.sep).index('DATA')+1]
                        # One case of updating the cursor failing ("input object is not a NADCON transformation") on
                        #  the cursor.updateRow(row) so wrapped in a try/except method.
                        try:
                            cursor.updateRow(row)
                            processed[os.path.join(path, raster)] = "Exists"
                        except:
                            # TODO: review files that failed and see if they need to be included.
                            print('\t\tUpdate cursor failed')
                            log.error('{}: update cursor failed'.format(os.path.join(path, raster)))
                            processed[os.path.join(path, raster)] = "Failed"
                            continue
                        print("\t\tRow updated\n")




def hash(path):
    '''
    Calculate the SHA256 hash for the file, where this is the case, or in the case of an ESRI File Geodatabase
    calculate the hash for files contained in the folder. For ESRI File Geodatabases all feature classes contained
    will have the same hash.
    :param path: path to the file or feature class
    :return: SHA256 hash value or 'sha256 hash failed'
    '''
    # calculate the SHA256 hash
    print('Hash function Path: {}'.format(path))
    print('\tpath exists: {}'.format(os.path.exists(path)))

    if r'gdb' in path:
        try:
            digest = hashlib.sha256()
            # print('path::: {}'.format(path))
            # Iterate through the GDB file content and produce a hash
            # split the path to get the fGDB - and therefore need to add 'gdb' to the end
            # print('\tpath split: {}'.format(path.split('gdb')[0] + 'gdb'))
            for root, folder, files in os.walk(path.split('gdb')[0] + 'gdb'):
                print('\tGenerating FGDB hash...')
                for f in files:
                    # print('\t\t{}'.format(f))
                    digest.update(hashlib.sha256(open(os.path.join(root, f), 'rb').read()).hexdigest())
                    # print('\t\t\tDigest update to: {}'.format(digest))
            h = digest.hexdigest()
            # print('\t\th digest: {}'.format(h))
        except:
            h = 'sha256 hash failed'
    else:
        try:
            print('\tGenerating hash value')
            h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
            print('\t\tHash generation successful')
        except:
            print('\t\tHash generation failed')
            h = 'sha256 hash failed'
    return h

def buildProcessedList(MD):
    """
    Build a list of paths to images previously added to the mosaic dataset.

    :param existingMosaicDataset: Path to existing mosaic dataset
    :return: List of paths
    """
    # TODO: Convert processed list to a dictionary for faster retrieval of data due to indexing of keys.
    # source: https://community.esri.com/thread/79933

    arcpy.MakeMosaicLayer_management(MD, 'mosaic')
    fc = r'mosaic\Footprint'
    field = ['path']

    with arcpy.da.SearchCursor(fc, field) as cursor:
        for row in cursor:
            processedList.append(row[0])
            #print(row[0])

    return processedList

def buildFailList(failDoc):
    '''
    Extracts failed file paths from the previous run log. This method has issues where file paths contain a ',' but
    still returns efficiency in not attempting to reload previously failed images to the mosaic dataset.
    :return:
    '''
    failList = []
    with open(failDoc, 'r') as f:
        x = f.readlines()
    for line in x:
        if line.split(',')[2] == "ERROR":
            processedList.append(line.split(',')[3].split(':')[0])
        elif line.split(',')[2] == "INFO":
            processedFolderList.append(line.split(',')[3].split(':')[0])
    return processedList
########################################################################################################################
### Mainline
########################################################################################################################

processedFolderList = []
parentFolderList = []
parentFolderInput = '1'
h = ''
hashCalc = False
continueProcess = ''
rasterCatalog = ''
failDoc = ''
outputLocation = ''
processedList = []
if __name__ == '__main__':
    while parentFolderInput != '':
        parentFolderInput = input("Parent folder: [enter on nil content to end path entry]")#sys.argv[1]
        parentFolderList.append(parentFolderInput)
    while not os.path.exists(outputLocation):
        outputLocation = input("Folder to store the output File Geodatabase and log file:")
    while h not in ['Y', 'N', 'y', 'n']:
        h = input("Calculate SHA256 hash for each image: [Y/N]")
    if h in ['Y', 'y']:
        hashCalc = True

    while continueProcess not in ['Y', 'N', 'y', 'n']:
        continueProcess = input("For single parent folder: continue process on an existing mosaic dataset: [Y/N]")
    if len(parentFolderInput) > 1 and continueProcess in ['Y', 'y']:
        print(r"Script can't process multiple parent folders and continue processing")
        sys.exit()
    if continueProcess in ['Y', 'y']:
        while not arcpy.Exists(rasterCatalog):
            rasterCatalog = input("Path to existing mosaic dataset:")
        processedList = buildProcessedList(rasterCatalog)
        print("{} files previously processed".format(len(processedList)))
        # process log doc of failures to previously load into mosaic dataset
        failDoc = input("Path to logfile of previous failed/processed mosaic dataset images:")
        if arcpy.Exists(failDoc):
            buildFailList(failDoc)
    for p in parentFolderInput.split(','):
        parentFolderList.append
    for parentFolder in parentFolderList:
        print(parentFolder)
        arcpy.env.workspace = parentFolder
        if not os.path.exists(parentFolder):
            sys.exit('Input path does not exist, exiting...')
        # Dictionary to store paths as keys
        processed = {}
        # Where you want to continue using an existing mosaic dataset to extend on, e.g. where the script crashed on
        #  a previous run.

        if continueProcess not in ['Y', 'y']:
            startTime = '{:%B%d_%Y_T%H%M}'.format(datetime.now())
            print(startTime)
            # Create FGDB and raster catalog
            fGDBName = "rasterExtentsChecked{}.gdb".format(startTime)
            print(os.path.join(outputLocation, fGDBName))
            print('FGDB creating: {}'.format(os.path.join(outputLocation, fGDBName)))
            arcpy.CreateFileGDB_management(outputLocation, fGDBName)
            print('FGDB created in {}'.format(os.path.join(parentFolder, fGDBName)))
            # Create the raster catalog. Will need to set the spatial grids and can do this once the data is loaded
            # raster catalog is created in the file geodatabase indicated (first parameter) which exists in the workspace
            arcpy.Exists(fGDBName)
            catalogName = "mosaicDataset"
            arcpy.CreateMosaicDataset_management(os.path.join(outputLocation,fGDBName), catalogName, arcpy.SpatialReference(4326))

            # Add the path field to the raster catalog
            rasterCatalog = os.path.join(outputLocation, fGDBName, catalogName)
            arcpy.env.workspace = os.path.join(outputLocation, fGDBName)
            arcpy.AddField_management(catalogName, 'path', 'TEXT', '', '', 255, '', '')
            arcpy.AddField_management(catalogName, 'SHA256Hash', 'TEXT', '', '', 255, '', '')
            arcpy.AddField_management(catalogName, 'DataType', 'TEXT', '', '', 255, '', '')
        else:
            startTime = '{:%B%d_%Y_T%H%M}'.format(datetime.now())
        # Set to True for logging to occur
        logging = True
        if logging:
            print("log file: {}".format(os.path.join(outputLocation, 'bounds_{}.log'.format(startTime)), ))
            log.basicConfig(
                level=log.INFO,  # Info and above get logged
                format='%(name)s,%(asctime)s,%(levelname)s,%(message)s',
                datefmt='%a %d %b %Y %H:%M:%S',
                filename=os.path.join(outputLocation, 'bounds_{}.log'.format(startTime)),
                filemode='w'  # write a new file each time this is run
            )
        # Flag so that the root is only checked for files on the first iteration. If this isn't included
        #  then duplicates occur in the mosaic dataset
        rootChecked = False

        for root, folders, files in os.walk(parentFolder, topdown=True):
            # slice out "~snapshot" folders from folders list, i.e. don't investigate ..\~snapshot
            folders[:] = [d for d in folders if d not in "~snapshot"]
            folders[:] = [d for d in folders if d not in "DEA_Data"]
            folders[:] = [d for d in folders if d not in "$RECYCLE.BIN"]
            # print('\n{}'.format(folders))
            # print('Folders: {}'.format(folders))
            for folder in folders:
                if folder == '~snapshot':
                    continue
                if os.path.join(root,folder) in processedFolderList:
                    print("Previously processed: {}".format(os.path.join(root, folder)))
                    log.info('{}: processed folder'.format(os.path.join(root, folder)))
                    continue
            if not rootChecked:
                # print("Finding rasters in root...{}".format(root))
                findRaster(root)
                rootChecked = True
            for folder in folders:
                # print("Finding rasters in folder...{}".format(folder))
                findRaster(os.path.join(root, folder))
                # TODO: Generate processed folder list from previous run log file and continue past these folders
                # TODO(cont): when rerunning. NOTE: this is not subfolders but for each folder content
                log.info('{}: processed folder'.format(os.path.join(root,folder)))
                # TODO: build code to exclude folder/subfolders (i.e. 'processed path' in os.path.join(root,folder)
                # TODO(cont): in the initial processed folder handling. This should not be a substring match as
                # TODO(cont): only the folder, and not subfolder content has been proceseed. This will speed up the
                # TODO(cont): process as individual paths to images will not need to be checked.

        print("{0} SCRIPT COMPLETE {0}".format(40 * '#'))


        # TODO: Set the default spatial index
        arcpy.env.workspace = os.path.join(outputLocation, fGDBName)
        arcpy.AddSpatialIndex_management(catalogName)
        # http://desktop.arcgis.com/en/arcmap/10.3/tools/data-management-toolbox/calculate-default-spatial-grid-index.htm
