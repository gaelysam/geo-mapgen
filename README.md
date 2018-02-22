# Geo Mapgen
Geo Mapgen is a (still experimental) mod for [Minetest](https://www.minetest.net/) that allows to generate map from digital elevation models like SRTM.

It is somewhat like [realterrain](https://forum.minetest.net/viewtopic.php?f=11&t=12666) but behaves differently: you need to run a separate Python file that transform the image into a database that is directly readable by Minetest. This solution was made to avoid running Lua libraries with Minetest (which is not recommended) or reading directly the image with the Lua API that is not made for that.

![Grand Canyon](https://user-images.githubusercontent.com/6905002/35072311-511f42e2-fbe4-11e7-839d-fbf2140e292a.png)

## Generating a map
### Finding data
This program doesn't come with pre-loaded geographical data, it only provides the tools to use them. You need to find your data on the Internet. All needs to be in an image format (usually GeoTIFF). The only mandatory data set is the topographical map, but you can also use additional maps for land cover or rivers.

#### Topographical data
You need topographical data, in the form of a Digital Elevation Model (DEM). It's an image that represents the terrain height for each point in a given area. There are several freely available DEMs, that differ in coverage, resolution, and quality.

I personally strongly recommand [SRTM](http://srtm.csi.cgiar.org/SELECTION/inputCoord.asp). It provides worldwide elevation tiles, that are not too big (6000² pixels, 1 px = 93 meters) and thus handy to work with, and are not projected.

#### Land cover data
Land cover support has been added last, this is something that has required much work, and unfortunately it still needs some work for the user to get it working.

To enable land cover, you need land cover data, in raster GeoTiff format. This is quite hard to find. A good reference for Europe is [Corine Land Cover](https://land.copernicus.eu/pan-european/corine-land-cover/clc-2012).

You also need to write a legend file, to decode the map. Geo Mapgen can't know which value matches which biome, and it has to be defined in a file (that I named `.lct`, for "Land Cover Table"). Its structure is the following:
```
1	urban
2	urban
3	industrial
4	industrial
5	industrial
6	industrial
7	rock
8	dirt
9	dirt
10	grass
11	dirt
12	fields
13	fields
14	fields
15	fields
```
Every line mean that one value in the data (for example 10) matches a particular land cover type recognized by Geo Mapgen (in this case "grass"). You need to find the legend of the map, and decide in which category every legend entry fits the most, and write the file. I've already written it for Corine Land Cover, in `clc.lct` (these are the 15 first lines), I can do it for other land cover maps if you kindly ask me ;)

List of biomes and land covers currectly supported by Geo Mapgen:
- industrial
- urban
- dirt
- grass
- dry_grass
- bushes
- scrub
- deciduous_forest
- coniferous_forest
- mixed_forest
- fields
- sand
- rock
- gravel
- water
- ice
- sea

#### River maps
River maps are mostly for advanced GIS users that are able to make such images from vector hydrographic data. It should represent the river network: every non-zero value will be interpreted as a river.

### Converting data
You must first convert the DEM image into a database, using the python script `image_convert.py` provided by this mod. You need a working Python 3 installation, with the following libraries:
- `numpy`
- `gdal`
- `tkinter`

Launch the script: go in geo-mapgen's directory, and run this:
```
./image_convert.py
```
You will see this interface:
![Interface](https://user-images.githubusercontent.com/6905002/36512379-7538a1a4-176a-11e8-86e1-4ddb4153399c.png)

Set the parameters (they are referenced below), and press *Proceed*. The conversion can take a moment, please be patient. You can see what happens in the console. When it prints "Done.", you can start your Minetest world.

## Complete list of parameters
### I/O Files
- *Elevation image*: Path to the GeoTIFF file for heightmap
- *Minetest world directory*: Path to the target (blank) Minetest world

### Region
To define the coverage of your map, and the sampling.

You have 3 options:
- *Don't modify the image*: Your map will have the same size than the image, that's to say 1 pixel = 1 node.
- *Crop image*: Keep only a part of the image. You can set the bounds by the N/E/S/O fields (in decimal degrees, real-world coordinates). With this option you still have 1 pixel = 1 node.
- *Crop and resample*: Keep a part of your image, and change pixel size. *Horizontal scale* is the size of one node in real meters.
At any moment, you can press *Calculate size* to know the size of your map with the current parameters.

**WARNING**: If you are using a very large image, make sure to resize the image so that your map is not too large (typically 15x15k pixels). Check with *Calculate size*. Otherwise, your computer may run out of memory.

### Generic parameters
- *Tiles size*: In the database, the image is cut into squares with a fixed size (by default 80 px) to make data searching faster. Changing ths size may have an impact on performance.
- *Vertical scale*: Number of real meters per node (default is 40), vertically. Can also be adjusted in the configuration file `heightmap.dat.conf`.

### Land Cover
*Land cover image*: path to your land cover image.

*Land cover legend file*: path to legend file, see above in **Land Cover Data** section.

### Rivers
Geo Mapgen can calculate automatically the positions of rivers with the elevation map, or load another image that will represent rivers.
- *Load from file*: if you have already generated a river map.
- *Calculate in-place*: Geo Mapgen can calculate automatically the positions of rivers, using topographical data to determine at every point in which direction water will flow. You can tweak some parameters: (if you don't understand it, leave them at default, they are fine)
  - *Minimal drainage basin*: Minimal size (area), in nodes, for the drainage basin at a given point, to be drawn as a river. Decrease it to draw more rivers.
  - *Maximal height difference*: Decrease river width if its valley is higher than this parameter. This has been made to avoid rivers completely fillind narrow gorges, since they are often drawn much wider than in reality.
  - *River widening power*: Rivers start with a size of 1 node, and can widen when joining together. This parameter controls how fast rivers widen when joining others. At 0, river size is never increased; at 1, it's the sum of its tributaries' size (which quickly become huge). Default to 0.25 is fine.
  - *Sea level*: Elevation (in meters) under which rivers are no more calculated.

Be aware that rivers calculation can be *very* slow (around 15 minutes for a 6000x6000 map).

## Additional information
Distributed under the GNU Lesser General Public License, version 2.1.
Code by Gael-de-Sailly (Gaël C.)
