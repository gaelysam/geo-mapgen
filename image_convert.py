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
gui = False
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
		if l == "g":
			gui = True
			i += 1
			continue
	else:
		if n == 2: # If this is the second argument
			fpath_output = arg
			n += 1
		if n == 1: # If this is the first
			fpath_input = arg
			n += 1
	i += 1

layer_count = 0 # Initialized

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
	heightmap = imageio.imread(fpath_input).newbyteorder("<")
	(Y, X) = heightmap.shape

	# Geometry stuff
	table_size_x, table_size_y = int(np.ceil(X / frag)), int(np.ceil(Y / frag))
	table_size = table_size_x * table_size_y

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
	file_output.write(header + data.getbuffer())
	file_output.close()

	file_conf.write("scale = " + str(scale))
	file_conf.close()

	print("Done.")

# GUI stuff
if gui:
	import tkinter as tk
	import tkinter.filedialog as fd

	root = tk.Tk()
	root.title("Geo Mapgen image converter")

	frame1 = tk.LabelFrame(root, text="I/O files")
	frame1.pack()
	frame2 = tk.LabelFrame(root, text="Generic parameters")
	frame2.pack()
	frame3 = tk.LabelFrame(root, text="Rivers")
	frame3.pack()

	input_var = tk.StringVar()
	input_var.set(fpath_input)
	input_entry = tk.Entry(frame1, textvariable=input_var, width=60)
	output_var = tk.StringVar()
	output_var.set(fpath_output)
	output_entry = tk.Entry(frame1, textvariable=output_var, width=60)
	input_entry.grid(row=0, column=1)
	output_entry.grid(row=1, column=1)
	tk.Label(frame1, text="Elevation image").grid(row=0, column=0, sticky="W")
	tk.Label(frame1, text="Minetest world directory").grid(row=1, column=0, sticky="W")

	def input_button_callback():
		input_var.set(fd.askopenfilename(title="Open elevation image"))
	def output_button_callback():
		output_var.set(fd.askdirectory(title="Open Minetest world"))

	input_button = tk.Button(frame1, text="Browse", command=input_button_callback)
	output_button = tk.Button(frame1, text="Browse", command=output_button_callback)
	input_button.grid(row=0, column=2)
	output_button.grid(row=1, column=2)

	tile_size_var = tk.IntVar()
	tile_size_var.set(frag)
	tile_size_spin = tk.Spinbox(frame2, from_=0, to=1024, textvariable=tile_size_var)
	tile_size_spin.grid(row=0, column=1)
	tk.Label(frame2, text="Tiles size").grid(row=0, column=0, sticky="W")

	scale_var = tk.DoubleVar()
	scale_var.set(scale)
	scale_spin = tk.Spinbox(frame2, from_=0, to=1000, textvariable=scale_var)
	scale_spin.grid(row=1, column=1)
	tk.Label(frame2, text="Vertical scale in meters per node").grid(row=1, column=0, sticky="W")

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
			river_input_entry.config(state=st1)
			river_input_button.config(state=st1)

			river_limit_spin.config(state=st2)
			river_limit_label.config(state=st2)
			river_hdiff_spin.config(state=st2)
			river_hdiff_label.config(state=st2)
			river_coeff_spin.config(state=st2)
			river_coeff_label.config(state=st2)
			sea_level_spin.config(state=st2)
			sea_level_label.config(state=st2)
		else:
			rivermode_rb1.config(state="disabled")
			rivermode_rb2.config(state="disabled")
			river_input_entry.config(state="disabled")
			river_input_button.config(state="disabled")
			river_limit_spin.config(state="disabled")
			river_limit_label.config(state="disabled")
			river_hdiff_spin.config(state="disabled")
			river_hdiff_label.config(state="disabled")
			river_coeff_spin.config(state="disabled")
			river_coeff_label.config(state="disabled")
			sea_level_spin.config(state="disabled")
			sea_level_label.config(state="disabled")

	river_cb_var = tk.BooleanVar()
	river_cb_var.set(rivers)
	river_cb_var.trace("w", river_gui_update)
	river_cb = tk.Checkbutton(frame3, text="Rivers", variable=river_cb_var)
	river_cb.grid(row=0, column=0)

	rivermode_rb_var = tk.IntVar()
	rivermode_rb_var.set(rivers_from_file)
	rivermode_rb_var.trace("w", river_gui_update)
	rivermode_rb1 = tk.Radiobutton(frame3, text="Load from file", variable=rivermode_rb_var, value=1)
	rivermode_rb1.grid(row=1, column=0)

	river_input_var = tk.StringVar()
	river_input_var.set(fpath_rivers)
	river_input_entry = tk.Entry(frame3, textvariable=river_input_var, width=60)
	river_input_entry.grid(row=1, column=1, columnspan=2)

	def river_input_button_callback():
		river_input_var.set(fd.askopenfilename())

	river_input_button = tk.Button(frame3, text="Browse", command=river_input_button_callback)
	river_input_button.grid(row=1, column=3)

	rivermode_rb2 = tk.Radiobutton(frame3, text="Calculate in-place (slow)", variable=rivermode_rb_var, value=0)
	rivermode_rb2.grid(row=2, column=0, rowspan=4)

	river_limit_var = tk.IntVar()
	river_limit_var.set(river_limit)
	river_limit_spin = tk.Spinbox(frame3, from_=0, to=1e6, increment=50, textvariable=river_limit_var)
	river_limit_spin.grid(row=2, column=2, sticky="W")
	river_limit_label = tk.Label(frame3, text="Minimal catchment area")
	river_limit_label.grid(row=2, column=1, sticky="W")

	river_hdiff_var = tk.DoubleVar()
	river_hdiff_var.set(max_river_hdiff)
	river_hdiff_spin = tk.Spinbox(frame3, from_=0, to=100, increment=1, textvariable=river_hdiff_var)
	river_hdiff_spin.grid(row=3, column=2, sticky="W")
	river_hdiff_label = tk.Label(frame3, text="Maximal height difference")
	river_hdiff_label.grid(row=3, column=1, sticky="W")

	river_coeff_var = tk.DoubleVar()
	river_coeff_var.set(coefficient)
	river_coeff_spin = tk.Spinbox(frame3, from_=0, to=2, increment=0.05, textvariable=river_coeff_var)
	river_coeff_spin.grid(row=4, column=2, sticky="W")
	river_coeff_label = tk.Label(frame3, text="River widening coefficient")
	river_coeff_label.grid(row=4, column=1, sticky="W")

	sea_level_var = tk.IntVar()
	sea_level_var.set(sea_level)
	sea_level_spin = tk.Spinbox(frame3, from_=-32768, to=65535, textvariable=sea_level_var)
	sea_level_spin.grid(row=5, column=2, sticky="W")
	sea_level_label = tk.Label(frame3, text="Sea level")
	sea_level_label.grid(row=5, column=1, sticky="W")

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
		global coefficient
		global sea_level
		global max_river_hdiff

		fpath_input = input_var.get()
		fpath_output = output_var.get()
		frag = tile_size_var.get()
		scale = scale_var.get()
		rivers = river_cb_var.get()
		rivers_from_file = rivermode_rb_var.get == 1
		fpath_rivers = river_input_var.get()
		river_limit = river_limit_var.get()
		coefficient = river_coeff_var.get()
		sea_level = sea_level_var.get()
		max_river_hdiff = river_hdiff_var.get()

		generate_database()

	proceed_button = tk.Button(root, text="Proceed", command = proceed)
	proceed_button.pack()

	tk.mainloop()

else:
	generate_database()
