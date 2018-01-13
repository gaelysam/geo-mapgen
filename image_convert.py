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
while i < n_args:
	arg = sys.argv[i]
	if len(arg) == 0:
		i += 1
		continue
	if arg[0] == "-":
		l = arg[1]
		if l == "f":
			frag = int(sys.argv[i+1])
			i += 2
			continue
		if l == "s":
			scale = float(sys.argv[i+1])
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
	signed = not dtype.kind == "u"

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

# Build file header
header = b'GEOMG' + version + s(np.uint16(frag)) + s(np.uint16(X)) + s(np.uint16(Y)) + s(np.uint8(layer_count))

# Write in files
file_output = open(fpath_output, "wb")
file_output.write(header + data.getbuffer())
file_output.close()

file_conf = open(fpath_conf, "w")
file_conf.write("scale = " + str(scale))
file_conf.close()
