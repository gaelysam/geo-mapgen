import numpy as np
import zlib
import io

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

version = b'\x01'

# Conversion to little endian
def le(n):
	return n.newbyteorder("<").tobytes()

layer_count = 0

def layer(data, datamap, datatype, frag, meta=b""): # Add a layer
	dtype = datamap.dtype
	itemsize = dtype.itemsize
	signed = dtype.kind == "i"

	(Y, X) = datamap.shape

	# Geometry stuff
	table_size_x, table_size_y = int(np.ceil(X / frag)), int(np.ceil(Y / frag))
	table_size = table_size_x * table_size_y

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
	layer_header = le(np.uint8(datatype)) + le(np.uint8(itemsize+signed*16)) + le(np.uint32(table_length)) + le(np.uint16(meta_length)) + meta

	# Add this to the main binary
	data.write(layer_header)
	data.write(layer_table_raw)
	data.write(layer_data.getbuffer())

	global layer_count
	layer_count += 1

def generate(file_output, file_conf, heightmap, rivermap=None, landmap=None, landmap_legend=None, frag=80, scale=40):
	global table_size
	print("Generating database")

	(Y, X) = heightmap.shape

	data = io.BytesIO() # This allows faster concatenation

	heightmap //= scale

	print("Adding heightmap")
	layer(data, heightmap, 0, frag)

	if type(rivermap) is not type(None):
		print("Adding rivermap")
		layer(data, rivermap, 1, frag)

	if type(landmap) is not type(None):
		print("Adding landcover")
		layer(data, landmap, 2, frag, meta=landmap_legend)

	print("Writing file")
	# Build file header
	header = b'GEOMG' + version + le(np.uint16(frag)) + le(np.uint16(X)) + le(np.uint16(Y)) + le(np.uint8(layer_count))

	# Write in files
	file_output.write(header + data.getbuffer())
	file_output.close()

	file_conf.write("scale = 1")
	file_conf.close()

	print("Done.")
