###############################################################################
# Aim: Find geotiffs (.tif files), and apply GDAL warp to:
#               - only tif files with a coordinate reference system are considered
#               - transform raster alignment to a north/south and east/west cell alignment (i.e. remove rotation/skew)
#
#   A "geoTiffWarp_{date/timestamp}" folder is created at the user specified, upon running the script this is requested, parent folder.
#   An iterative folder search is carried out for all files with a '.tif' ending. GeoTiffs are then saved via GDAL
#   warp to the same projection but in the datestamp folder. This removes the skew. The python script and a log file
#   is saved to the datestamp folder
#
# This script does not work in PyCharm 2018 calling osgeo through Anaconda package. Instead, run the script in
# Anaconda shell which includes the osgeo package.
#
# Useful open source Python reference https://livebook.manning.com/book/geoprocessing-with-python/chapter-3/126
#
#
# Duncan Moore,  16 December 2021
###############################################################################

# Import required libraries
from osgeo import gdal
from osgeo import osr
import os
import sys
import datetime
import time
import shutil
import logging as log


def rasterCharacteristics(raster):
    '''
    Input is
    :param raster: GDAL raster object
    :return: Raster characteristics defined in a dictionary: 'ulx': upper left x coordinatel, 'uly': upper left
    coordinate, 'xres': x resolution, 'yres': y resolution, 'xskew': x skew, 'yskew': y skew, 'srs': well-known text
    representation of the coordinate reference system, 'prj': projection.
    '''

    ulx, xscale, xskew, uly, yskew, yscale = raster.GetGeoTransform()
    print(raster.GetGeoTransform())
    print(f'\t\tband count: {raster.RasterCount}')
    print(f'\t\tUpper left x: {ulx}')
    print(f'\t\tUpper left y: {uly}')
    print(f'\t\tX skew: {xskew}')
    print(f'\t\tY skew: {yskew}')
    # Square root of x resolution square plus y skew squared
    # Source: https://gis.stackexchange.com/questions/281132/why-doesnt-gdalinfo-report-pixel-size
    if xscale != 0:
        # Square root of x resolution squared plus y skew squared
        # Source: https://gis.stackexchange.com/questions/281132/why-doesnt-gdalinfo-report-pixel-size
        xres = round((xscale**2 + yskew**2)**0.5, 8)
    else:
        xres = xscale
    if yscale != 0:
        # Square root of y resolution squared plus x skew squared
        # Source: https://gis.stackexchange.com/questions/281132/why-doesnt-gdalinfo-report-pixel-size
        yres = round((yscale**2 + xskew**2)**0.5, 8)
    else:
        yres = yscale
    print(f'\t\tX resolution: {xres}')
    print(f'\t\tY resolution: {yres}')

    md = raster.GetMetadata()
    # print(f'\t\tMetadata: {md}')

    # Get the Coordinate Reference System (CRS) of the layer
    proj = raster.GetProjection()
    srs = osr.SpatialReference(wkt=proj)

    if srs.IsProjected:
        prj = srs.GetAttrValue('projcs')
    else:
        prj = srs.GetAttrValue('geogcs')

    vals = {'ulx': ulx, 'uly': uly, 'xres': xres, 'yres': yres, 'xskew': xskew, 'yskew': yskew, 'srs': srs, 'prj': prj}
    return vals

# Set intial time
t0 = time.time()

# parentFolder from which all content within subfolders is searched for s57 data
parentFolder = input("Enter the top folder to search within for GeoTiff (.tif) data: ")
while not os.path.exists(f'{parentFolder}'):  # Test to make sure an input was provided
    print('No existing top folder provided...')
    parentFolder = input("\tEnter the top folder: ")

# Create folder to store coastline extracts with a date time stamp
folderDateTime = f"_{datetime.datetime.now().strftime('%d_%m_%Y_%Hh%Mm%Ss')}"
outFolder = os.path.join(os.path.split(parentFolder)[0],
                         f'geoTiffWarp_{folderDateTime}')

outFolder = os.path.join(parentFolder, f'geoTiffWarp_{folderDateTime}')
print(f'Results in {outFolder}')
# sys.exit()
os.mkdir(outFolder)
# Save the script to the outFolder to store with the outputs
shutil.copy2(sys.argv[0], outFolder)

# Establish the log file
logfile = os.path.join(outFolder, rf'geoTiffWarp_logfile_{folderDateTime}.log')
print(f'Logfile in: {logfile}')

# os.path.join(os.path.split(workspace)[0],r'logfile.log')
log.basicConfig(filename=logfile,
                level=log.DEBUG,
                filemode='w',  # 'w' = overwrite log file, 'a' = append
                format='%(asctime)s,   Line:%(lineno)d %(levelname)s: %(message)s',
                datefmt='%a %d/%b/%Y %I:%M:%S %p')
# Log the path and name of the script used to the logfile
log.info('Script started: ' + sys.argv[0])
# Log the parent folder to the logfile
log.info('Parent folder to find s57 data within: ' + parentFolder)

# Flag that sets to True once the memory layer is used. User not required to change this.
memLayersUsed = False

# Initiate empty lists to contain the path to geotiffs and for non-georeferenced tiff files
geotifList = []

# Identify and process GeoTiffs to remove X and Y skew through projecting to source projection
# TODO: consider whether resampling would achieve the same result
for root, folder, files in os.walk(parentFolder):
    for f in files:
        # s57 data files end with a '000' extension.
        if f.endswith('tif'):
            # Ignore previous raster outputs (they're saved with a '_warp.tip' end.
            if '_warp.tif' in f:
                continue
            filePath = os.path.join(root, f)
            print(f'Tiff: {filePath}')
            ds = gdal.Open(filePath)
            print(f'\tSource raster characteristics:')
            sourceVals = rasterCharacteristics(ds)

            log.info(f'Tiff: {f}: path: {filePath}')

            # Get the Coordinate Reference System (CRS) of the layer
            proj = ds.GetProjection()
            srs = osr.SpatialReference(wkt=proj)
            # print(f'Proj: {proj}')
            # print(f'Proj type: {type(proj)}')

            print(f'\t\tProjection: {sourceVals["prj"]}')
            if sourceVals["prj"] is not None:
                geotifList.append(filePath)
                log.info('Geotiff found, projection: {prj}')
                outputFile = os.path.join(outFolder, f'{os.path.split(filePath)[1].split(".")[0]}_warp.tif')
                warp = gdal.Warp(outputFile, filePath, dstSRS=proj, xRes=sourceVals['xres'], yRes=sourceVals['yres'],# xRes=sourceVals['xres']*-1, yRes=sourceVals['yres']
                               targetAlignedPixels=True)# 'EPSG:4326'
                print(f'\tProjected to original CRS: {outputFile}')
                log.info(f'Projected to original CRS: {outputFile}')
                ds = gdal.Open(outputFile)
                print(f'\tOutput raster characteristics:')
                outputVals = rasterCharacteristics(ds)
                print(f'\t\tProjection: {outputVals["prj"]}')
                print()

            else:
                log.info('No projection, this file no longer considered')
                print('No projection, this file no longer considered\n')

print(f'\n{len(geotifList)} GeoTiffs found:')
for geotiff in geotifList:
    print(f'\t{geotiff}')

print(f'\nScript completed in {round((time.time() - t0)/60, 2)} minutes')

log.info(f'{len(geotifList)} GeoTiff files found')
log.info(f'Script completed in {round((time.time() - t0)/60, 2)} minutes')

print('Script complete.')

