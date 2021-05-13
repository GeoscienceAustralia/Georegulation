########################################################################################################################
# The purpose of this script is to build a list of tif files within a single folder and mosaic the images together.
#
#
# Duncan Moore 12 May 2021
########################################################################################################################

import time
t0 = time.time()
print('Script started...')

import arcpy
import os
import sys
import shutil

print(f'\tModules imported: {round(time.time() - t0, 2)} seconds')

folder = input("Enter the folder to search within for tif files: ")
# name for the folder and the mosaic tif file
name = input("Enter the name for the folder which will also be used for the tif file:")
outputFolder = os.path.join(os.path.split(folder)[0], name)

if not os.path.exists(folder):
    sys.exit('Input folder does not exist')

# Create outputFolder if it does not exist.
if not os.path.exists(outputFolder):
    os.mkdir(outputFolder)

# Save the script to the outFolder to store with the outputs
shutil.copy2(sys.argv[0], outputFolder)

# Coordinate Reference System dictionary. Key is CRS, value is a list of file name(s)
crsDict = {}

# list all the tif files in the folder
fileList = []
# TODO: Consider saving the dictionary to a pickle file as it takes a while to recomplete the list/dictionary production
# TODO:  if multiple runs are expected
for (root, folders, files) in os.walk(folder):
    for file in files:
        if file.endswith('tif'):
            print(f'\t{file}')
            fileList.append(file)
            crs = arcpy.Describe(os.path.join(root,file)).spatialReference
            if crs.name not in crsDict.keys():
                crsDict[crs.name] = [file]
            else:
                crsDict[crs.name].append(file)
    # break so as not to delve into any subfolders within folder
    break

print(crsDict)

# Check to see if there are more than one CRS being used so as to consider the CRS for the mosaic tif file and/or
# transforming/projecting the input tif files to a common CRS. ArcGIS Pro may transform/project within the mosaic process
if len(crsDict) != 1:
    print('\nWARNING: More than one CRS, need to consider the output CRS for the mosaic...')
    for key, values in crsDict.items():
        print(f'\t{key}, count: {len(values)}')
    # sys.exit('More than one CRS, need to consider the output CRS for the mosaic...')

# Mosaic the images to a new tif file
# Set the workspace
arcpy.env.workspace = folder

# Build the ';' separated input tifs
print('Building file name string input...')
inputTifs = ';'.join(fileList)
print('\tDone.')
#
print('Starting mosaic process...')
arcpy.MosaicToNewRaster_management(inputTifs, outputFolder, f"{name}.tif",\
                                   pixel_type='8_BIT_UNSIGNED', mosaic_method='FIRST', number_of_bands=3)

print(f'Script finished ({(round(time.time() - t0)/60, 2)} minutes)')
