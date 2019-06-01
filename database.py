import numpy as np
import zlib
from osgeo import osr, gdal
import io
import os

# Database structure: (all is little endian)
# HEADER:
# 	0-4	"GEOMG"
# 	5	Version
# 	6-7	Fragmentation
# 	8-9	Horizontal size in px
# 	10-11	Vertical size in px
#	12-13	Length of projection descriptor
#	14-A	Projection descriptor (Proj-4 format)
#	A+1-48	Geotransform (6 floats)
#	A+49	Number of layers
# LAYER1:
#	HEADER:
#		0	Layer type
#		1	Number type (see below)
#		2-5	Length of table
#		6-7	Length of metadata
#		METADATA
#	TABLE:
#		4-bytes address of every chunk, zlib compressed
#	DATA:
#		chunk1:
#			raw data, bytes per pixel depend on 'itemsize'
#		chunk2:
#			...
#		...
# LAYER2:
#	...

# Number types:
#	0 for unsigned int
#	16 for signed int
#	32 for float
#	+ length in bytes

#	e.g. int32 = 16 (int) + 4 bytes = 20

version = b'\x02'

def get_ntype(dtype):
	k = dtype.kind
	i = dtype.itemsize
	if k == 'u':
		return i
	elif k == 'i':
		return i+0x10
	elif k == 'f':
		return i+0x20

def get_dtype(ntype):
	k, i = np.divmod(ntype, 16)
	if k == 0:
		ntype = 'u'
	elif k == 1:
		ntype = 'i'
	elif k == 2:
		ntype = 'f'
	if ntype:
		return np.dtype(ntype + str(i))

# Conversion to little endian
def le(n):
	return n.newbyteorder("<").tobytes()

memdrv = gdal.GetDriverByName("MEM")
tifdrv = gdal.GetDriverByName("GTiff")

class Layer:
	def __init__(self, dataset, layer_type=0, metadata='', interp=0, dtype=None):
		self.type = layer_type
		self.metadata = metadata
		self.interp = interp
		if isinstance(dataset, gdal.Dataset):
			self.dataset = dataset
		else:
			self.dataset = gdal.Open(dataset)
		self.dtype = dtype

		"""
		if len(args) >= 1:
			data = args[0]
			if isinstance(data, str):
				self.dataset = gdal.Open(data)
			elif isinstance(data, gdal.Dataset):
				self.dataset = data
			elif isinstance(data, io.IOBase):
				self.load(data, frag=frag)
		"""

	"""
	def load(self, obj, frag=128):
		self.type = obj.read(1)[0]
		dtype = get_dtype(obj.read(1)[0])
		table_length = int(np.fromstring(obj.read(4), 'u4'))
		meta_length = int(np.fromstring(obj.read(2), 'u2'))
		self.metadata = obj.read(meta_length).decode()

		table = np.fromstring(zlib.decompress(obj.read(table_length)), 'u4')

		i = 0
		for address in table:
			chunk = np.frombuffer(zlib.decompress(obj.read(address-i)), dtype).reshape(frag, frag)
			i = address
	"""

	def get_parameters(self, wanted):
		params = {}
		ds = self.dataset
		if 'proj' in wanted:
			proj = osr.SpatialReference()
			proj.ImportFromWkt(ds.GetProjection())
			params['proj'] = proj.ExportToProj4()
		if 'geotransform' in wanted:
			params['geotransform'] = ds.GetGeoTransform()
		if 'X' in wanted:
			params['X'] = ds.RasterXSize
		if 'Y' in wanted:
			params['Y'] = ds.RasterYSize
		return params

	def generate(self, obj, frag=128, proj=None, geotransform=None, X=None, Y=None, use_temp_file=False):
		ds = self.dataset
		ds_proj = osr.SpatialReference()
		ds_proj.ImportFromWkt(ds.GetProjection())
		ds_gt = ds.GetGeoTransform()

		reproject = False

		if proj is None or ds_proj.ExportToProj4() == proj:
			target_proj = ds_proj
		else:
			reproject = True
			target_proj = osr.SpatialReference()
			target_proj.ImportFromProj4(proj)

		if geotransform is None or geotransform == ds_gt:
			target_gt = ds_gt
		else:
			reproject = True
			target_gt = geotransform

		if X is None:
			X = ds.RasterXSize
		if Y is None:
			Y = ds.RasterYSize

		if reproject:
			if use_temp_file:
				drv = tifdrv
				name = "temp.tif"
			else:
				drv = memdrv
				name = ""

			new_ds = drv.Create(name, X, Y, 1, ds.GetRasterBand(1).DataType)
			new_ds.SetGeoTransform(target_gt)
			gdal.ReprojectImage(ds, new_ds, ds_proj.ExportToWkt(), target_proj.ExportToWkt(), self.interp)
		else:
			new_ds = ds

		array = new_ds.GetTiledVirtualMemArray(tilexsize=frag, tileysize=frag)
		if self.dtype is None:
			dtype = array.dtype
		else:
			dtype = np.dtype(self.dtype)
		dtype = dtype.newbyteorder('<')

		tiles_y, tiles_x = array.shape[:2]
		table = np.zeros(tiles_x*tiles_y, dtype='<u4')

		data = io.BytesIO()
		n = 0
		i = 0
		array_callback = self.on_array_save
		for row in array:
			for tile in row:
				scaled_tile = array_callback(tile).astype(dtype)
				n += data.write(zlib.compress(scaled_tile.tobytes(), 9))
				table[i] = n
				i += 1

		del array
		if reproject:
			del new_ds
			if use_temp_file:
				os.remove("temp.tif")

		table_bytes = zlib.compress(table.tobytes(), 9)
		metadata = self.metadata.encode()

		header =  le(np.uint8(self.type)) + le(np.uint8(get_ntype(dtype))) + le(np.uint32(len(table_bytes))) + le(np.uint16(len(metadata))) + metadata

		return obj.write(header) + obj.write(table_bytes) + obj.write(data.getbuffer())

	def on_array_save(self, array): # Function to be redefined by subclasses
		return array

class Heightmap(Layer):
	def __init__(self, dataset, scale=1, **kwargs):
		Layer.__init__(self, dataset, **kwargs)
		self.type = 0
		self.scale = scale

	def on_array_save(self, array):
		if self.scale == 1:
			return array
		else:
			return array*self.scale

class Database:
	def __init__(self, proj=None, geotransform=None, X=None, Y=None):
		self.layers = {}
		self.proj = proj
		self.geotransform = geotransform
		self.X = X
		self.Y = Y
		self.version = version

		"""
		if len(args) >= 1:
			data = args[0]
			if isinstance(data, str):
				with open(args[0], 'rb') as f:
					self.load(f)
			elif isinstance(data, io.IOBase):
				self.load(data)
		"""

	"""
	def load(self, obj):
		if obj.read(5) != b'GEOMG':
			print("WARNING: File signature not recognized!")

		self.version = obj.read(1)[0]
		self.frag = int(np.fromstring(obj.read(2), 'u2'))
		self.X = int(np.fromstring(obj.read(2), 'u2'))
		self.Y = int(np.fromstring(obj.read(2), 'u2'))
		layer_count = obj.read(1)[0]
		proj_length = int(np.fromstring(obj.read(2), 'u2'))
		self.proj = obj.read(proj_length).decode()
		self.geotransform = tuple(np.fromstring(obj.read(48), 'f8').tolist())

		for i in range(layer_count):
			layer = Layer(obj)
			self.layers[layer.type] = layer
	"""

	def add_layer(self, layer):
		self.layers[layer.type] = layer

	def write(self, filename, **kwargs):
		with open(filename, 'wb') as f:
			self.generate(f, **kwargs)

	def generate(self, obj, frag=128, use_temp_file=False):
		params = self.layers[0].get_parameters({'proj', 'geotransform', 'X', 'Y'})
		if self.proj is not None:
			params['proj'] = self.proj
		if self.geotransform is not None:
			params['geotransform'] = self.geotransform
		if self.X is not None:
			params['X'] = self.X
		if self.Y is not None:
			params['Y'] = self.Y

		params['X'] = int(np.ceil(params['X']/frag))*frag
		params['Y'] = int(np.ceil(params['Y']/frag))*frag

		bproj = params['proj'].encode()

		header = b'GEOMG' + version + le(np.uint16(frag)) + le(np.uint16(params['X'])) + le(np.uint16(params['Y'])) + le(np.uint16(len(bproj))) + bproj + le(np.float64(params['geotransform'])) + le(np.uint8(len(self.layers)))

		n = obj.write(header)

		for layer in self.layers.values():
			n += layer.generate(obj, frag=frag, use_temp_file=use_temp_file, **params)

		return n
