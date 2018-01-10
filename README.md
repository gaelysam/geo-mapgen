# Geo Mapgen
Geo Mapgen is a (still experimental) mod for [Minetest](https://www.minetest.net/) that allows to generate map from digital elevation models like [SRTM](http://srtm.csi.cgiar.org/SELECTION/inputCoord.asp).

It is somewhat like [realterrain](https://forum.minetest.net/viewtopic.php?f=11&t=12666) but behaves differently: you need to run a separate Python file that transform the image into a database that is directly readable by Minetest. This solution was made to avoid running Lua libraries with Minetest (which is not recommended) or reading directly the image with the Lua API that is not made for that.

## Usage
You must first convert the DEM image into a database, using the python script `image_convert.py` provided by this mod. You need a working Python installation, with libraries `numpy` and `imageio`.

This will generate 2 files in the world directory: `heightmap.dat` which is the database, and `heightmap.dat.conf`, configuration file working with the database.

Syntax for the Python script:
```
image_convert.py input_file.tif minetest_world_directory [-f fragmentation] [-s scale]
```
Note that even if TIFF files are the most commonly used, any image with only one color channel can be loaded by this script.

In the database, the image is cut into squares with a fixed size (usually 80 px) to make data searching faster. If you want a different size, you can specify it with `-f`.

Scale is the number of real meters per node, vertically (by default 40).

Example of use:
```
./image_convert.py '/home/gael/dem/srtm_38_04.tif' '/home/gael/.minetest/worlds/bidule' -f 100 -s 90
```
The conversion may take several minutes.

Once the files are generated, you can start playing.

## Additional information
Distributed under the GNU Lesser General Public License, version 2.1.
Code by Gael-de-Sailly (Gaël C.)
