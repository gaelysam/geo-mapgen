import geometry as gm
try:
	from osgeo import gdal, osr
except ImportError:
	import gdal
	import osr
import numpy as np

mercator = osr.SpatialReference()
mercator.ImportFromEPSG(3857)
wgs = osr.SpatialReference()
wgs.ImportFromEPSG(4326)
merc_transform = osr.CreateCoordinateTransformation(wgs, mercator)

drv = gdal.GetDriverByName("MEM")

maps = {}
maps_paths = {}

param_reproject = False
param_crop = False
param_region = None
param_hscale = 100.0

def set_parameters(reproject=None, crop=None, region=None, hscale=None):
	global param_reproject, param_crop, param_region, param_hscale
	if reproject != None:
		param_reproject = reproject
	if crop != None:
		param_crop = crop
	if region != None:
		param_region = region
	if hscale != None:
		param_hscale = hscale

def update_map(mapname, newfilepath):
	if mapname in maps_paths and maps_paths[mapname] == newfilepath:
		return
	try:
		maps[mapname] = gdal.Open(newfilepath)
		maps_paths[mapname] = newfilepath
	except:
		print("Path", newfilepath, "is not a valid map.")	

def get_map_size(mapname):
	if mapname in maps:
		thismap = maps[mapname]
	else:
		print("Map", mapname, "does not exist.")
		return
	if param_region:
		if param_reproject:
			north, east, south, west = param_region
			minp = merc_transform.TransformPoint(west, south)
			maxp = merc_transform.TransformPoint(east, north)
			pxsize = param_hscale / np.cos(np.radians((north+south)/2))
			npx = (maxp[0]-minp[0]) // pxsize
			npy = (maxp[1]-minp[1]) // pxsize
			return int(npx), int(npy), 0, 0, pxsize
		else:
			gt = thismap.GetGeoTransform()
			proj = osr.SpatialReference()
			proj.ImportFromWkt(thismap.GetProjection())
			transform = osr.CreateCoordinateTransformation(wgs, proj)
			north, east, south, west = param_region
			xNW, yNW = gm.inverse(gt, transform.TransformPoint(west, north))
			xSE, ySE = gm.inverse(gt, transform.TransformPoint(east, south))
			xmin = np.floor(min(xNW, xSE)+.5)
			xmax = np.floor(max(xNW, xSE)+.5)
			ymin = np.floor(min(yNW, ySE)+.5)
			ymax = np.floor(max(yNW, ySE)+.5)
			return int(xmax-xmin+1), int(ymax-ymin+1), int(xmin), int(ymin), 0
	else:
		return thismap.RasterXSize, thismap.RasterYSize, 0, 0, 0

def read_map(mapname, interp=gdal.GRA_NearestNeighbour):
	npx, npy, xmin, ymin, pxsize = get_map_size(mapname)
	if mapname in maps:
		map1 = maps[mapname]
	else:
		return

	if not param_reproject:
		return map1.ReadAsArray(xmin, ymin, npx, npy)
	north, east, south, west = param_region
	origin = merc_transform.TransformPoint(west, north)
	geotransform = (origin[0], pxsize, 0., origin[1], 0., -pxsize)
	print(geotransform)

	map2 = drv.Create("", npx, npy, 1, map1.GetRasterBand(1).DataType)
	map2.SetGeoTransform(geotransform)
	gdal.ReprojectImage(map1, map2, map1.GetProjection(), mercator.ExportToWkt(), interp)
	return map2.ReadAsArray()
