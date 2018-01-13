#!/usr/bin/env python3

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
i = 1
n = 1
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
		if n == 2:
			fpath_output = arg
			n += 1
		if n == 1:
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

layer_count = 1

# Binary conversion stuff
def s(n):
	return n.newbyteorder("<").tobytes()

# Data tables
data = io.BytesIO()
header = b'GEOMG' + version + s(np.uint16(frag)) + s(np.uint16(X)) + s(np.uint16(Y)) + s(np.uint8(layer_count))
data.write(header)

def layer(datamap):
	dtype = datamap.dtype
	itemsize = dtype.itemsize
	signed = not dtype.kind == "u"

	layer_table = np.zeros(table_size, dtype=np.uint32).newbyteorder("<")
	layer_data = io.BytesIO()
	i = 0
	n = 0
	for y in range(0, Y, frag):
		for x in range(0, X, frag):
			part = datamap[y:y+frag,x:x+frag]
			part_raw = part.tobytes()
			n += layer_data.write(zlib.compress(part_raw, 9))
			layer_table[i] = n
			i += 1

	layer_table_raw = zlib.compress(layer_table.tobytes(), 9)
	table_length = len(layer_table_raw)
	layer_header = s(np.uint8(0)) + s(np.uint8(itemsize+signed*16)) + s(np.uint32(table_length))

	data.write(layer_header)
	data.write(layer_table_raw)
	data.write(layer_data.getbuffer())

layer(heightmap)

# File structure: (all is little endian)
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

file_output = open(fpath_output, "wb")
file_output.write(data.getbuffer())
file_output.close()

file_conf = open(fpath_conf, "w")
file_conf.write("scale = " + str(scale))
file_conf.close()
