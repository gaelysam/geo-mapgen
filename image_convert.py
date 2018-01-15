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

version = b'\x00'

# Deal with argv
fpath_input = None
fpath_output = None

n_args = len(sys.argv)
i = 1 # Start at 1 because argv[0] is the script name
n = 1 # Number of arguments not preceded by parameter name
frag = 80
scale = 40.
rivers = False
rivers_from_file = False
fpath_rivers = None
river_limit = 1000
coefficient = 0.25 # When water quantity is multiplied by t, river width is multiplied by t ^ coefficient
sea_level = -128
max_river_hdiff = 40
while i < n_args:
	arg = sys.argv[i]
	if len(arg) == 0:
		i += 1
		continue
	if arg[0] == "-":
		l = arg[1]
		if l == "l":
			sea_level = int(sys.argv[i+1])
			i += 2
			continue
		if l == "f":
			frag = int(sys.argv[i+1])
			i += 2
			continue
		if l == "s":
			scale = float(sys.argv[i+1])
			i += 2
			continue
		if l == "r":
			rivers = True
			try:
				river_limit = int(sys.argv[i+1])
			except ValueError: # If the parameter is not a number, it's interpreted as a file path.
				rivers_from_file = True
				fpath_rivers = sys.argv[i+1]
			i += 2
			continue
		if l == "c":
			coefficient = float(sys.argv[i+1])
			i += 2
			continue
		if l == "d":
			max_river_hdiff = int(sys.argv[i+1])
			i += 2
			continue
		if l == "i":
			fpath_input = sys.argv[i+1]
			i += 2
			continue
		if l == "o":
			fpath_output = sys.argv[i+1]
			i += 2
			continue
	else:
		if n == 2: # If this is the second argument
			fpath_output = arg
			n += 1
		if n == 1: # If this is the first
			fpath_input = arg
			n += 1
	i += 1

# File paths stuff
if not fpath_input:
	raise ValueError("No filename given for input")

if not fpath_output:
	raise ValueError("No filename given for output")

fpath_output += "/heightmap.dat"
fpath_conf = fpath_output + ".conf"

# Load the first file
heightmap = imageio.imread(fpath_input).newbyteorder("<")
(Y, X) = heightmap.shape

# Geometry stuff
table_size_x, table_size_y = int(np.ceil(X / frag)), int(np.ceil(Y / frag))
table_size = table_size_x * table_size_y

layer_count = 0

data = io.BytesIO() # This allows faster concatenation

# Binary conversion stuff
def s(n):
	return n.newbyteorder("<").tobytes()

def layer(datamap, datatype): # Add a layer
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
	layer_header = s(np.uint8(datatype)) + s(np.uint8(itemsize+signed*16)) + s(np.uint32(table_length))

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

		to_explore = 0

		for x in range(1, X-1):
			for y in range(1, Y-1):
				if heightmap[y, x] <= sea_level:
					continue
				to_explore += 1
				if to_explore % 1000000 == 0:
					print("Found", str(to_explore // 1000000), "× 10⁶ points to explore")
				if (heightmap[y, x-1] <= sea_level or heightmap[y, x+1] <= sea_level or heightmap[y-1, x] <= sea_level or heightmap[y+1, x] <= sea_level):
					add_start_point(y, x)

		for x in range(X):
			if heightmap[0, x] > sea_level:
				add_start_point(0, x)
				to_explore += 1
			if heightmap[-1, x] > sea_level:
				add_start_point(Y-1, x)
				to_explore += 1

		for y in range(1, Y-1):
			if heightmap[y, 0] > sea_level:
				add_start_point(y, 0)
				to_explore += 1
			if heightmap[y, -1] > sea_level:
				add_start_point(y, X-1)
				to_explore += 1

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
				rsize = int((q / river_limit)**coefficient)
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
file_output = open(fpath_output, "wb")
file_output.write(header + data.getbuffer())
file_output.close()

file_conf = open(fpath_conf, "w")
file_conf.write("scale = " + str(scale))
file_conf.close()
