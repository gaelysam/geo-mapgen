#!/usr/bin/env python3

# This script is made to convert a Digital Elevation Model image (usually GeoTIFF) into a database, readable by Minetest to generate real terrain.

import tkinter as tk
import tkinter.filedialog as fd
import tkinter.simpledialog as sd
import functools

import map_transform
import database
import rivers
from landcover import make_landcover

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
	def trace(self, mode, callback):
		self.var.trace(mode, callback)

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
frame_landcover = tk.LabelFrame(root, text="Land Cover")
frame_landcover.pack()
frame_rivers = tk.LabelFrame(root, text="Rivers")
frame_rivers.pack()

def input_projection(mapname):
	return sd.askinteger("Projection", "GDAL has failed to detect projection automatically.\nPlease set here the EPSG number of the projection\nused by "+mapname+".")

def file_map_update(mapname, file_entry, *args):
	fpath = file_entry.get()
	map_transform.update_map(mapname, fpath, get_proj=input_projection)

def get_update_callback(entry, mapname):
	return functools.partial(file_map_update, mapname, entry)

input_entry = FileEntry(frame_files, "file", row=0, column=0, text="Elevation image", dialog_text="Open elevation image")
output_entry = FileEntry(frame_files, "dir", row=1, column=0, text="Minetest world directory", dialog_text="Open Minetest world")
input_entry.trace("w", get_update_callback(input_entry, "heightmap"))

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

def set_to_fullsize(*args):
	north, east, south, west = map_transform.get_map_bounds("heightmap")
	north_entry.set(north)
	east_entry.set(east)
	south_entry.set(south)
	west_entry.set(west)
fullsize_button = tk.Button(frame_region, text="Full map size", command=set_to_fullsize)
fullsize_button.grid(row=0, column=1, rowspan=3, columnspan=3, sticky="S")

region_gui_update()

def update_parameters():
	value = region_rb_var.get()
	if value == 0:
		map_transform.set_parameters(reproject=False, crop=False, reference="heightmap")
	if value >= 1:
		if value == 2:
			reproject=True
		else:
			reproject=False

		north, east, south, west, hscale = north_entry.get(), east_entry.get(), south_entry.get(), west_entry.get(), hscale_entry.get()
		map_transform.set_parameters(reproject=reproject, crop=True, region=(north, east, south, west), hscale=hscale)

def map_size_update(*args):
	update_parameters()

	npx, npy, _, _, _ = map_transform.get_map_size()
	map_size_label.config(text="{:d} x {:d}".format(int(npx), int(npy)))

calc_button = tk.Button(frame_region, text="Calculate size", command=map_size_update)
map_size_label.grid(row=6, column=3)
calc_button.grid(row=6, column=2)

tile_size_entry = NumberEntry(frame_params, 0, 1024, row=0, column=0, text="Tiles size", default=80)
scale_entry = NumberEntry(frame_params, 0, 1000, row=1, column=0, text="Vertical scale in meters per node", default=40)

def landcover_gui_update(*args):
	if landcover_cb_var.get():
		st = "normal"
	else:
		st = "disabled"
	landcover_input_entry.set_state(st)
	landcover_legend_entry.set_state(st)

landcover_cb_var = tk.BooleanVar()
landcover_cb_var.set(False)
landcover_cb_var.trace("w", landcover_gui_update)
landcover_cb = tk.Checkbutton(frame_landcover, text="Enable Land Cover", variable=landcover_cb_var)
landcover_cb.grid(row=0, column=0)

landcover_input_entry = FileEntry(frame_landcover, "file", row=1, column=0, text="Land cover image", dialog_text="Open land cover image")
landcover_legend_entry = FileEntry(frame_landcover, "file", row=2, column=0, text="Land cover legend file", dialog_text="Open land cover legend")
landcover_input_entry.trace("w", get_update_callback(landcover_input_entry, "landcover"))

landcover_gui_update()

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
river_cb_var.set(False)
river_cb_var.trace("w", river_gui_update)
river_cb = tk.Checkbutton(frame_rivers, text="Rivers", variable=river_cb_var)
river_cb.grid(row=0, column=0)

rivermode_rb_var = tk.IntVar()
rivermode_rb_var.set(0)
rivermode_rb_var.trace("w", river_gui_update)
rivermode_rb1 = tk.Radiobutton(frame_rivers, text="Load from file", variable=rivermode_rb_var, value=1)
rivermode_rb1.grid(row=1, column=0)

river_input_entry = FileEntry(frame_rivers, "file", row=1, column=1, columnspan=2, dialog_text="Open river image")
river_input_entry.trace("w", get_update_callback(river_input_entry, "rivermap"))

rivermode_rb2 = tk.Radiobutton(frame_rivers, text="Calculate in-place (slow)", variable=rivermode_rb_var, value=0)
rivermode_rb2.grid(row=2, column=0, rowspan=4)

river_limit_entry = NumberEntry(frame_rivers, 0, 1e6, incr=50, row=2, column=1, text="Minimal drainage basin", default=1000)
river_hdiff_entry = NumberEntry(frame_rivers, 0, 100, row=3, column=1, text="Maximal height difference", default=40, is_float=True)
river_power_entry = NumberEntry(frame_rivers, 0, 2, incr=0.05, row=4, column=1, text="River widening power", default=0.25, is_float=True)
sea_level_entry = NumberEntry(frame_rivers, -32768, 65535, row=5, column=1, text="Sea level", default=-128)

river_gui_update()

def proceed():
	fpath_output = output_entry.get()
	fpath_output += "/heightmap.dat"
	fpath_conf = fpath_output + ".conf"
	# Load files at the beginning, so that if a path is wrong, the user will know it instantly.
	file_output = open(fpath_output, "wb")
	file_conf = open(fpath_conf, "w")

	update_parameters()
	
	heightmap = map_transform.read_map("heightmap", interp=4) # Read with Lanczos interpolation (code 4)
	if river_cb_var.get():
		rivers_from_file = rivermode_rb_var.get() == 1
		if rivers_from_file:
			rivermap = map_transform.read_map("rivers", interp=8)
		else:
			river_limit = river_limit_entry.get()
			river_power = river_power_entry.get()
			sea_level = sea_level_entry.get()
			max_river_hdiff = river_hdiff_entry.get()
			rivermap = rivers.generate_rivermap(heightmap, sea_level=sea_level, river_limit=river_limit, river_power=river_power)
	else:
		rivermap = None

	if landcover_cb_var.get():
		fpath_legend = landcover_legend_entry.get()
		landmap_raw = map_transform.read_map("landcover", interp=0)
		landmap, legend = make_landcover(landmap_raw, fpath_legend)
	else:
		landmap = None
		legend = None

	tile_size = tile_size_entry.get()
	scale = scale_entry.get()	
	database.generate(file_output, file_conf, heightmap, rivermap=rivermap, landmap=landmap, landmap_legend=legend, frag=tile_size, scale=scale)

proceed_button = tk.Button(root, text="Proceed", command = proceed)
proceed_button.pack()

tk.mainloop()
