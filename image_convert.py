#!/usr/bin/env python3

import sys
import numpy as np
import imageio
import zlib

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

if not fpath_input:
	raise ValueError("No filename given for input")

if not fpath_output:
	raise ValueError("No filename given for output")

fpath_output += "/heightmap.dat"
fpath_conf = fpath_output + ".conf"

heightmap = imageio.imread(fpath_input).newbyteorder("<")
dtype = heightmap.dtype
itemsize = dtype.itemsize
signed = not dtype.kind == "u"

shape = heightmap.shape
(X, Y) = shape

table_size_x, table_size_y = int(np.ceil(X / frag)), int(np.ceil(Y / frag))
table_size = table_size_x * table_size_y
table = np.zeros(table_size, dtype=np.uint32).newbyteorder("<")
data = b''
i = 0
for x in range(0, X, frag):
	for y in range(0, Y, frag):
		part = heightmap[x:x+frag,y:y+frag]
		part_data = part.tobytes()
		data += zlib.compress(part_data, 9)
		table[i] = len(data)
		i += 1

data_table = zlib.compress(table.tobytes(), 9)

table_length = len(data_table)

# File structure: (all is little endian)
# HEADER:
# 	0-4	"IMGEN"
# 	5	Bytes per point (+16 if signed)
# 	6-7	Fragmentation
# 	8-9	Horizontal size in px
# 	10-11	Vertical size in px
# 	12-15	length of table
# TABLE:
#	4-bytes address of every chunk, zlib compressed
# DATA:
#	chunk1:
#		raw data, bytes per pixel depend on 'itemsize'
#	chunk2:
#		...
#	...

header = b'GEOMG' + np.uint8(itemsize+signed*16).newbyteorder("<").tobytes() + np.uint16(frag).newbyteorder("<").tobytes() + np.uint16(X).newbyteorder("<").tobytes() + np.uint16(Y).newbyteorder("<").tobytes() + np.uint32(table_length).newbyteorder("<").tobytes()

file_output = open(fpath_output, "wb")
file_output.write(header + data_table + data)
file_output.close()

file_conf = open(fpath_conf, "w")
file_conf.write("scale = " + str(scale))
file_conf.close()
