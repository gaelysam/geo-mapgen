#!/usr/bin/env python3

# This script is made to convert a Digital Elevation Model image (usually GeoTIFF) into a database, readable by Minetest to generate real terrain.

# Database structure: (all is little endian)
# HEADER:
# 	0-4	"GEOMG"
# 	5	Version
# 	6-7	Fragmentation
# 	8-9	Horizontal size in px
# 	10-11	Vertical size in px
#	12	Number of layers
# LAYER1:
#	HEADER:
#		0	Data type
#		1	Bytes per point (+16 if signed)
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

import sys
import numpy as np
import imageio
import zlib
import io
try:
	from osgeo import gdal, osr
except ImportError:
	import gdal
	import osr

version = b'\x01'

# Deal with argv
fpath_input = None
fpath_output = None

# Initialize variables
frag = 80
scale = 40.
rivers = False
rivers_from_file = False
fpath_rivers = None
river_limit = 1000
river_power = 0.25 # When water quantity is multiplied by t, river width is multiplied by t ^ river_power
sea_level = -128
max_river_hdiff = 40

layer_count = 0 # Initialized

mercator = osr.SpatialReference()
mercator.ImportFromEPSG(3857)
wgs = osr.SpatialReference()
wgs.ImportFromEPSG(4326)
transform = osr.CreateCoordinateTransformation(wgs, mercator)

drv = gdal.GetDriverByName("MEM")

def make_heightmap(fpath, region=None, interp=gdal.GRA_NearestNeighbour):
	crop = False
	if region:
		crop = True
		north, east, south, west, hscale = region

	dem1 = gdal.Open(fpath)
	dem1b = dem1.GetRasterBand(1)

	minp = transform.TransformPoint(west, south)
	maxp = transform.TransformPoint(east, north)

	print(hscale)

	pxsize = hscale / np.cos(np.radians((north+south) / 2))

	npx = int((maxp[0]-minp[0]) // pxsize)
	npy = int((maxp[1]-minp[1]) // pxsize)

	print(npx, npy, pxsize)

	geotransform = (minp[0], pxsize, 0., maxp[1], 0., -pxsize)

	print(dem1.GetGeoTransform(), geotransform)

	dem2 = drv.Create("", npx, npy, 1, dem1b.DataType)
	dem2.SetGeoTransform(geotransform)
	gdal.ReprojectImage(dem1, dem2, dem1.GetProjection(), mercator.ExportToWkt(), interp)
	return dem2.ReadAsArray()

def generate_database():
	global fpath_output

	# File paths stuff
	if not fpath_input:
		raise ValueError("No filename given for input")

	if not fpath_output:
		raise ValueError("No filename given for output")

	fpath_output += "/heightmap.dat"
	fpath_conf = fpath_output + ".conf"

	# Load files at the beginning, so that if a path is wrong, the user will know it instantly.
	file_output = open(fpath_output, "wb")
	file_conf = open(fpath_conf, "w")

	# Load the first file
	#heightmap = imageio.imread(fpath_input).newbyteorder("<")
	north, east, south, west, hscale = north_entry.get(), east_entry.get(), south_entry.get(), west_entry.get(), hscale_entry.get()
	heightmap = make_heightmap(north, east, south, west, hscale, interp=gdal.GRA_Lanczos)
	print(heightmap.dtype)
	(Y, X) = heightmap.shape
	print(X, Y)

	print(np.min(heightmap))

	# Geometry stuff
	table_size_x, table_size_y = int(np.ceil(X / frag)), int(np.ceil(Y / frag))
	table_size = table_size_x * table_size_y

	data = io.BytesIO() # This allows faster concatenation

	# Binary conversion stuff
	def s(n):
		return n.newbyteorder("<").tobytes()

	def layer(datamap, datatype, meta=b""): # Add a layer
		dtype = datamap.dtype
		itemsize = dtype.itemsize
		signed = dtype.kind == "i"

		layer_table = np.zeros(table_size, dtype=np.uint32).newbyteorder("<") # Table will be a list of the position of every chunk in the data section
		layer_data = io.BytesIO()
		i = 0
		n = 0
		for y in range(0, Y, frag):
			for x in range(0, X, frag):
				part = datamap[y:y+frag,x:x+frag] # Take only the chunk x;y
				part_raw = part.tobytes() # Convert it into binary
				n += layer_data.write(zlib.compress(part_raw, 9)) # Add this to the binary buffer, and increment n by the number of bytes
				layer_table[i] = n # Sets the position of the end of the chunk
				i += 1

		layer_table_raw = zlib.compress(layer_table.tobytes(), 9) # Compress the table too
		table_length = len(layer_table_raw)
		meta_length = len(meta)
		layer_header = s(np.uint8(datatype)) + s(np.uint8(itemsize+signed*16)) + s(np.uint32(table_length)) + s(np.uint16(meta_length)) + meta

		# Add this to the main binary
		data.write(layer_header)
		data.write(layer_table_raw)
		data.write(layer_data.getbuffer())

		global layer_count
		layer_count += 1

	layer(heightmap, 0)

	if rivers:
		if rivers_from_file:
			river_array = imageio.imread(fpath_rivers) > 0
		else:
			from heapq import heappush, heappop, heapify
			sys.setrecursionlimit(65536)

			print("[rivers]: Finding start points")

			visited = np.zeros((Y,X), dtype=bool)

			start_points = []

			def add_start_point(y,x):
				start_points.append((heightmap[y, x] + np.random.random(), y, x))
				visited[y, x] = True

			def find_start_points(t, x=1, y=1):
				sy, sx = t.shape
				if t.all() or not t.any():
					return
				if max(sx, sy) == 3:
					if (not t[1,1]) and (t[0,1] or t[1,0] or t[1,2] or t[2,1]):
						add_start_point(y,x)
					return
				if sx < sy:
					cut = sy//2
					find_start_points(t[:cut+1,:], x=x, y=y)
					find_start_points(t[cut-1:,:], x=x, y=y+cut-1)
				else:
					cut = sx//2
					find_start_points(t[:,:cut+1], x=x, y=y)
					find_start_points(t[:,cut-1:], x=x+cut-1, y=y)

			seas = heightmap <= sea_level
			find_start_points(seas)

			to_explore = X * Y - np.count_nonzero(seas)

			for x in np.flatnonzero(~seas[0,:]):
				add_start_point(0, x)
			for x in np.flatnonzero(~seas[-1,:]):
				add_start_point(Y-1, x)
			for y in np.flatnonzero(~seas[1:-1,0]):
				add_start_point(y, 0)
			for y in np.flatnonzero(~seas[1:-1,-1]):
				add_start_point(y, -1)

			del seas

			print("Found", str(len(start_points)), "start points")

			heap = start_points[:]
			heapify(heap)

			print("Building river trees:", str(to_explore), "points to visit")

			flow_dirs = np.zeros((Y, X), dtype=np.int8)

			# Directions:
			#	1: +x
			#	2: +y
			#	4: -x
			#	8: -y

			def try_push(y, x): # try_push does 2 things at once: returning whether water can flow, and push the upward position in heap if yes.
				if not visited[y, x]:
					h = heightmap[y, x]
					if h > sea_level:
						heappush(heap, (h + np.random.random(), y, x))
						visited[y, x] = True
						return True
				return False

			def process_neighbors(y, x):
				dirs = 0
				if x > 0 and try_push(y, x-1):
					dirs+= 1
				if y > 0 and try_push(y-1, x):
					dirs += 2
				if x < X-1 and try_push(y, x+1):
					dirs += 4
				if y < Y-1 and try_push(y+1, x):
					dirs += 8
				flow_dirs[y, x] = dirs

			while len(heap) > 0:
				t = heappop(heap)
				to_explore -= 1
				if to_explore % 1000000 == 0:
					print(str(to_explore // 1000000), "× 10⁶ points remaining", "Altitude:", int(t[0]), "Queue:", len(heap))
				process_neighbors(t[1], t[2])

			visited = None

			print("Calculating water quantity")

			waterq = np.ones((Y, X))
			river_array = np.zeros((Y, X), dtype=bool)

			def draw_river(x, y, q):
				if q >= river_limit:
					rsize = int((q / river_limit)**river_power)
					if rsize > 1:
						hmax = heightmap[y,x] + max_river_hdiff
						rsize -= 1
						xmin = max(x-rsize, 0)
						xmax = min(x+rsize+1, X)
						ymin = max(y-rsize, 0)
						ymax = min(y+rsize+1,Y)
						river_array[y,xmin:xmax] += heightmap[y,xmin:xmax] <= hmax
						river_array[ymin:ymax,x] += heightmap[ymin:ymax,x] <= hmax
					else:
						river_array[y,x] = True

			def set_water(y, x):
				water = 1
				dirs = flow_dirs[y, x]

				if dirs % 2 == 1:
					water += set_water(y, x-1)
				dirs //= 2
				if dirs % 2 == 1:
					water += set_water(y-1, x)
				dirs //= 2
				if dirs % 2 == 1:
					water += set_water(y, x+1)
				dirs //= 2
				if dirs % 2 == 1:
					water += set_water(y+1, x)
				waterq[y, x] = water

				if water >= river_limit:
					draw_river(x, y, water)
				return water

			maxwater = 0
			for start in start_points:
				water = set_water(start[1], start[2])
				if water > maxwater:
					maxwater = water

			print("Maximal water quantity:", str(maxwater))

			flow_dirs = None

		layer(river_array, 1)

	# Build file header
	header = b'GEOMG' + version + s(np.uint16(frag)) + s(np.uint16(X)) + s(np.uint16(Y)) + s(np.uint8(layer_count))

	# Write in files
	file_output.write(header + data.getbuffer())
	file_output.close()

	file_conf.write("scale = " + str(scale))
	file_conf.close()

	print("Done.")

# GUI stuff

import tkinter as tk
import tkinter.filedialog as fd

root = tk.Tk()
root.title("Geo Mapgen image converter")

class WidgetGroup:
	def get(self):
		return self.var.get()
	def set(self, v):
		self.var.set(v)
	def set_state(self, state):
		for widget in self.widgets:
			widget.config(state=state)

class FileEntry(WidgetGroup):
	def __init__(self, parent, iotype, row=0, column=0, columnspan=1, sticky="W", text=None, default="", dialog_text="Open"):
		self.var = tk.StringVar()
		self.var.set(default)
		self.entry = tk.Entry(parent, textvariable=self.var, width=60)
		if iotype == "file":
			callback = self.browse_files
		elif iotype == "dir":
			callback = self.browse_dirs
		self.button = tk.Button(parent, text="Browse", command=callback)
		if text:
			self.label = tk.Label(parent, text=text)
			self.label.grid(row=row, column=column, sticky=sticky)
			self.has_label = True
			self.widgets = [self.entry, self.button, self.label]
			column += 1
		else:
			self.has_label = False
			self.widgets = [self.entry, self.button]
		self.entry.grid(row=row, column=column, columnspan=columnspan)
		column += columnspan
		self.button.grid(row=row, column=column)
		self.dialog_text = dialog_text

	def browse_files(self):
		self.var.set(fd.askopenfilename(title=self.dialog_text))

	def browse_dirs(self):
		self.var.set(fd.askdirectory(title=self.dialog_text))

class NumberEntry(WidgetGroup):
	def __init__(self, parent, mini, maxi, incr=1, row=0, column=0, columnspan=1, sticky="W", text=None, default=0, is_float=False):
		if is_float:
			self.var = tk.DoubleVar()
		else:
			self.var = tk.IntVar()
		self.var.set(default)
		self.spinbox = tk.Spinbox(parent, from_=mini, to=maxi, increment=incr, textvariable=self.var, width=8)
		if text:
			self.label = tk.Label(parent, text=text)
			self.label.grid(row=row, column=column, sticky=sticky)
			self.has_label = True
			self.widgets = [self.spinbox, self.label]
			column += 1
		else:
			self.has_label = False
			self.widgets = [self.spinbox]
		self.spinbox.grid(row=row, column=column, columnspan=columnspan)

frame_files = tk.LabelFrame(root, text="I/O files")
frame_files.pack()
frame_region = tk.LabelFrame(root, text="Region")
frame_region.pack()
frame_params = tk.LabelFrame(root, text="Generic parameters")
frame_params.pack()
frame_rivers = tk.LabelFrame(root, text="Rivers")
frame_rivers.pack()

input_entry = FileEntry(frame_files, "file", row=0, column=0, text="Elevation image", default=fpath_input, dialog_text="Open elevation image")
output_entry = FileEntry(frame_files, "dir", row=1, column=0, text="Minetest world directory", default=fpath_output, dialog_text="Open Minetest world")

def region_gui_update(*args):
	value = region_rb_var.get()
	state1 = "disabled"
	state2 = "disabled"
	if value >= 1:
		state1 = "normal"
		if value >= 2:
			state2 = "normal"
	north_entry.set_state(state1)
	east_entry.set_state(state1)
	south_entry.set_state(state1)
	west_entry.set_state(state1)
	hscale_entry.set_state(state2)

region_rb_var = tk.IntVar()
region_rb_var.set(0)
region_rb_var.trace("w", region_gui_update)
region_rb1 = tk.Radiobutton(frame_region, text="Don't modify the image", variable=region_rb_var, value=0)
region_rb2 = tk.Radiobutton(frame_region, text="Crop image", variable=region_rb_var, value=1)
region_rb3 = tk.Radiobutton(frame_region, text="Crop and resample", variable=region_rb_var, value=2)
region_rb1.grid(row=0, column=0, sticky="W")
region_rb2.grid(row=1, column=0, sticky="W")
region_rb3.grid(row=2, column=0, sticky="W")
north_entry = NumberEntry(frame_region, -90, 90, row=3, column=1, sticky="E", text="N", is_float=True)
west_entry = NumberEntry(frame_region, -180, 180, row=4, column=0, sticky="E", text="W", is_float=True)
east_entry = NumberEntry(frame_region, -180, 180, row=4, column=2, sticky="E", text="E", is_float=True)
south_entry = NumberEntry(frame_region, -90, 90, row=5, column=1, sticky="E", text="S", is_float=True)
hscale_entry = NumberEntry(frame_region, 0, 10000, row=6, column=0, text="Horizontal scale", is_float=True)
map_size_label = tk.Label(frame_region, text="")

region_gui_update()

def map_size_update(*args):
	value = region_rb_var.get()
	if value == 2:
		north, east, south, west = north_entry.get(), east_entry.get(), south_entry.get(), west_entry.get()
		minp = transform.TransformPoint(west, south)
		maxp = transform.TransformPoint(east, north)
		pxsize = hscale_entry.get() / np.cos(np.radians((north+south)/2))
		npx = (maxp[0]-minp[0]) // pxsize
		npy = (maxp[1]-minp[1]) // pxsize
	
	map_size_label.config(text="{:d} x {:d}".format(int(npx), int(npy)))

calc_button = tk.Button(frame_region, text="Calculate size", command=map_size_update)
map_size_label.grid(row=6, column=3)
calc_button.grid(row=6, column=2)

tile_size_entry = NumberEntry(frame_params, 0, 1024, row=0, column=0, text="Tiles size", default=frag)
scale_entry = NumberEntry(frame_params, 0, 1000, row=1, column=0, text="Vertical scale in meters per node", default=scale)

def river_gui_update(*args):
	if river_cb_var.get():
		rivermode_rb1.config(state="normal")
		rivermode_rb2.config(state="normal")
		if rivermode_rb_var.get() == 1:
			st1 = "normal"
			st2 = "disabled"
		else:
			st1 = "disabled"
			st2 = "normal"
		river_input_entry.set_state(st1)
		river_limit_entry.set_state(st2)
		river_hdiff_entry.set_state(st2)
		river_power_entry.set_state(st2)
		sea_level_entry.set_state(st2)
	else:
		st = "disabled"
		rivermode_rb1.config(state="disabled")
		rivermode_rb2.config(state="disabled")
		river_input_entry.set_state(st)
		river_limit_entry.set_state(st)
		river_hdiff_entry.set_state(st)
		river_power_entry.set_state(st)
		sea_level_entry.set_state(st)

river_cb_var = tk.BooleanVar()
river_cb_var.set(rivers)
river_cb_var.trace("w", river_gui_update)
river_cb = tk.Checkbutton(frame_rivers, text="Rivers", variable=river_cb_var)
river_cb.grid(row=0, column=0)

rivermode_rb_var = tk.IntVar()
rivermode_rb_var.set(rivers_from_file)
rivermode_rb_var.trace("w", river_gui_update)
rivermode_rb1 = tk.Radiobutton(frame_rivers, text="Load from file", variable=rivermode_rb_var, value=1)
rivermode_rb1.grid(row=1, column=0)

river_input_entry = FileEntry(frame_rivers, "file", row=1, column=1, columnspan=2, default=fpath_rivers, dialog_text="Open river image")

rivermode_rb2 = tk.Radiobutton(frame_rivers, text="Calculate in-place (slow)", variable=rivermode_rb_var, value=0)
rivermode_rb2.grid(row=2, column=0, rowspan=4)

river_limit_entry = NumberEntry(frame_rivers, 0, 1e6, incr=50, row=2, column=1, text="Minimal catchment area", default=river_limit)
river_hdiff_entry = NumberEntry(frame_rivers, 0, 100, row=3, column=1, text="Maximal height difference", default=max_river_hdiff, is_float=True)
river_power_entry = NumberEntry(frame_rivers, 0, 2, incr=0.05, row=4, column=1, text="River widening power", default=river_power, is_float=True)
sea_level_entry = NumberEntry(frame_rivers, -32768, 65535, row=5, column=1, text="Sea level", default=sea_level)

river_gui_update()

def proceed():
	global fpath_input
	global fpath_output
	global frag
	global scale
	global rivers
	global rivers_from_file
	global fpath_rivers
	global river_limit
	global river_power
	global sea_level
	global max_river_hdiff

	fpath_input = input_entry.get()
	fpath_output = output_entry.get()
	frag = tile_size_entry.get()
	scale = scale_entry.get()
	rivers = river_cb_var.get()
	rivers_from_file = rivermode_rb_var.get() == 1
	fpath_rivers = river_input_entry.get()
	river_limit = river_limit_entry.get()
	river_power = river_power_entry.get()
	sea_level = sea_level_entry.get()
	max_river_hdiff = river_hdiff_entry.get()

	generate_database()

proceed_button = tk.Button(root, text="Proceed", command = proceed)
proceed_button.pack()

tk.mainloop()
