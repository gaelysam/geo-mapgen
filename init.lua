local path = "heightmap.dat"
local conf_path = "heightmap.dat.conf"

local worldpath = minetest.get_worldpath()
local modpath = minetest.get_modpath(minetest.get_current_modname())

file = io.open(worldpath .. "/" .. path)
local conf = Settings(worldpath .. "/" .. conf_path)

-- Configuration
local scale_x = tonumber(conf:get("scale_x")) or 1
local scale_y = tonumber(conf:get("scale_y")) or conf:get("scale") or 1
local scale_z = tonumber(conf:get("scale_z")) or 1
local offset_x = tonumber(conf:get("offset_x")) or 0
local offset_y = tonumber(conf:get("offset_y")) or 0
local offset_z = tonumber(conf:get("offset_z")) or 0

local function get_bool(name)
	local v = conf:get_bool(name)
	if v == nil then
		return true -- Enable by default, disable only if explicitly set to false
	end
	return false
end

local enable_rivers = get_bool("rivers")
local enable_landcover = get_bool("landcover")
local enable_trees = get_bool("trees")
local enable_plants = get_bool("plants")

local remove_delay = 10 -- Number of mapgen calls until a chunk is unloaded

-- Load proj lib (if allowed by mod security)
local ie = minetest.request_insecure_environment()
local projlib
if ie then
	projlib = ie.require("proj")
	if projlib then
		print("[geo_mapgen] Using Lua proj library")
	else
		print("[geo_mapgen] Could not find Lua proj library")
	end
else
	print("[geo_mapgen] WARNING: Loading of proj library blocked by mod security. Some extra features like teleporting to a location will not be available.")
end

-- Load geotransform lib
local GeoTransform = dofile(modpath .. "/" .. "geotransform.lua")

-- Load number lib
local num = dofile(modpath .. "/" .. "readnumber.lua")
local readn = num.readnumber

if file:read(5) ~= "GEOMG" then
	print('[geo_mapgen] WARNING: file may not be in the appropriate format. Signature "GEOMG" not recognized.')
end

local version = readn(file:read(1), num.uint8)
if projlib and version < 2 then
	print('[geo_mapgen] Georeferencing not available for this database version.')
end

-- Geometry stuff
local frag = readn(file:read(2), num.uint16)
local X = readn(file:read(2), num.uint16)
local Z = readn(file:read(2), num.uint16)
local chunks_x = math.ceil(X / frag) -- Number of chunks along X axis
local chunks_z = math.ceil(Z / frag) -- Number of chunks along Z axis

local xmin = math.ceil(offset_x)
local xmax = math.floor(X*scale_x+offset_x)
local zmin = math.ceil(-Z*scale_z+offset_z)
local zmax = math.floor(offset_z)

local game_to_map = GeoTransform(offset_x, scale_x, 0, offset_z, 0, -scale_z):reverse()

local last_chunk_length = (X-1) % frag + 1 -- Needed for incrementing index because last chunk may be truncated in length and therefore need an unusual increment

local function displaytime(time)
	return math.floor(time * 1000000 + 0.5) / 1000 .. " ms"
end

-- Metatables
local function load_chunk(layer, n)
	print("[geo_mapgen]   Loading chunk " .. n)
	local t1 = os.clock()

	local index = layer.index
	local address_min = index[n-1] -- inclusive
	local address_max = index[n] -- exclusive
	local count = address_max - address_min
	file:seek("set", layer.offset + address_min)
	local data_raw = minetest.decompress(file:read(count))
	layer[n] = data_raw -- Put raw data in table
	layer.delay[n] = remove_delay -- Set delay for this chunk
	
	local t2 = os.clock()
	print("[geo_mapgen]   Loaded chunk " .. n .. " in " .. displaytime(t2-t1))
	return data_raw
end

local mt = {__index = load_chunk} -- Metatable that will allow to load chunks on request

local delays = {} -- Will be a list of delay tables. A delay table is a table that contains the delay before unload of every loaded chunk.

local heightmap = nil
local rivermap = nil
local rivers = false
local biomemap = nil
local biomes = false
local biome_list = {}

-- Projection parameters
local proj, map_to_proj
if version >= 2 then
	local proj_length = readn(file:read(2), num.uint16)
	proj = file:read(proj_length)
	map_to_proj = GeoTransform(readn(file:read(48), num.float64))
end

-- Layers
local datatypes = {
	[0x01] = num.uint8,
	[0x02] = num.uint16,
	[0x04] = num.uint32,
	[0x08] = num.uint64,
	[0x11] = num.int8,
	[0x12] = num.int16,
	[0x14] = num.int32,
	[0x18] = num.int64,
	[0x22] = num.float16,
	[0x24] = num.float32,
	[0x28] = num.float64,
}

local layers = {}
local layer_count = readn(file:read(1), num.uint8)
for l=1, layer_count do
	local layertype = readn(file:read(1), num.uint8) -- Type of data: 0 = heightmap, 1 = rivermap
	local datatype = datatypes[readn(file:read(1), num.uint8)]
	local itemsize = datatype[1]

	local index_length = readn(file:read(4), num.uint32)
	local meta = ""
	if version >= 1 then
		local meta_length = readn(file:read(2), num.uint16)
		meta = file:read(meta_length)
	end

	local index = {readn(minetest.decompress(file:read(index_length)), num.uint32)}
	index[0] = 0 -- Variable is called index instead of table to avoid name conflicts. Will contain a list of the ending position for every chunk, begin at chunk 1, so (unexisting) chunk 0 would end at pos 0. This makes simpler the calculation of chunk size that is index[i] - index[i-1] even for i=1.

	local delay = {} -- Delay table, will contain the number of mapgen calls before unloading, for every loaded chunk
	delays[l] = delay

	local layer = {
		delay = delay,
		offset = file:seek(), -- Position of first data
		itemsize = itemsize,
		datatype = datatype,
		index = index,
		meta = meta,
	}

	delay.data = layer -- Reference layer in delay table

	setmetatable(layer, mt)

	if layertype == 0 then -- Code for heightmap
		heightmap = layer
	elseif layertype == 1 then
		print("Rivermap enabled!")
		rivermap = layer
		rivers = enable_rivers
	elseif layertype == 2 then
		print("Biomemap enabled!")
		biomemap = layer
		biomes = enable_landcover

		local biomes_by_name = dofile(modpath .. "/landcover.lua") -- Load biome descriptions
		local biomenames = meta:split(',', true)
		for i, name in ipairs(biomenames) do
			biome_list[i] = biomes_by_name[name]
		end
	end

	local data_size = index[#index]
	file:seek("cur", data_size) -- Skip data and go to the position of the next layer
end

local function choose_deco(decos)
	local r = math.random()
	for _, deco_params in ipairs(decos) do
		local prob = deco_params.prob
		if r < prob then
			local deco = deco_params.deco
			return deco.list[math.random(#deco.list)], deco.is_schem
		else
			r = r - prob
		end
	end
end

local data = {}

minetest.register_on_mapgen_init(function(mgparams)
	minetest.set_mapgen_params({mgname="singlenode", flags="nolight"})
end)

-- Timing stuff
local mapgens = 0
local time_sum = 0
local time_sum2 = 0

-- Decode the value of a chunk for a given pixel
local function value(layer, nchunk, n)
	local itemsize = layer.itemsize
	return readn(layer[nchunk]:sub((n-1)*itemsize + 1, n*itemsize), layer.datatype)
end

minetest.register_on_generated(function(minp, maxp, seed)
	print("[geo_mapgen] Generating from " .. minetest.pos_to_string(minp) .. " to " .. minetest.pos_to_string(maxp))
	local t0 = os.clock()

	local c_stone = minetest.get_content_id("default:stone")
	local c_dirt = minetest.get_content_id("default:dirt")
	local c_lawn = minetest.get_content_id("default:dirt_with_grass")
	local c_water = minetest.get_content_id("default:water_source")
	local c_rwater = minetest.get_content_id("default:river_water_source")

	local vm, emin, emax = minetest.get_mapgen_object("voxelmanip")
	vm:get_data(data)
	local a = VoxelArea:new({MinEdge = emin, MaxEdge = emax})
	local ystride = a.ystride

	local schems_to_generate = {}

	for x = math.max(xmin, minp.x), math.min(xmax, maxp.x) do
	for z = math.max(zmin, minp.z), math.min(zmax, maxp.z) do
		local ivm = a:index(x, minp.y, z)

		local xmap, zmap = game_to_map(x, z)
		xmap, zmap = math.floor(xmap), math.floor(zmap)

		local xchunk = math.floor(xmap / frag)
		local zchunk = math.floor(zmap / frag)
		local nchunk = xchunk + zchunk * chunks_x + 1
		
		local increment = frag
		if xchunk + 1 == chunks_x then -- Last chunk of the line: may be truncated, that would change the line increment.
			increment = last_chunk_length
		end
		local xpx = xmap % frag
		local zpx = zmap % frag
		local npx = xpx + zpx * increment + 1 -- Increment is used here

		local h = math.floor(value(heightmap, nchunk, npx) * scale_y + offset_y)

		if minp.y <= math.max(h,offset_y) then
			local river_here = false
			if rivers then
				river_here = value(rivermap, nchunk, npx) > 0
			end
			local stone, filler, top = c_stone, c_dirt, c_lawn
			local nfiller, ntop = 3, 1
			local node_deco
			if biomes and h >= offset_y then
				local nbiome = value(biomemap, nchunk, npx)
				local biome = biome_list[nbiome]
				if biome then
					stone = biome.stone
					filler = biome.filler
					top = biome.top
					nfiller = biome.filler_depth
					ntop = biome.top_depth
					if enable_plants and maxp.y >= h and not river_here then -- Generate decoration
						local deco, is_schem = choose_deco(biome.decos)
						if deco then
							if is_schem then
								if enable_trees then
									table.insert(schems_to_generate, {pos={x=x-2,y=h+1,z=z-2}, schem=deco}) -- Schem size is not known. Assuming that most of schematics have a size of 5, hardcode offset to 2. TODO: Change that when schematic flags will be available on minetest.place_schematic_on_vmanip
								end
							else
								node_deco = deco
							end
						end
					end
				end
			end

			if h < offset_y then
				top = filler
			end

			local stone_min = minp.y
			local stone_max = math.min(h-nfiller, maxp.y)
			local filler_min = math.max(stone_max+1, minp.y)
			local filler_max = math.min(h-ntop, maxp.y)
			local top_min = math.max(filler_max+1, minp.y)
			local top_max = math.min(h, maxp.y)

			if river_here then
				top_max = math.min(h-1, maxp.y)
			end

			if stone_min <= stone_max then
				for y = stone_min, stone_max do
					data[ivm] = stone
					ivm = ivm + ystride
				end
			end

			if filler_min <= filler_max then
				for y = filler_min, filler_max do
					data[ivm] = filler
					ivm = ivm + ystride
				end
			end

			if top_min <= top_max then
				for y = top_min, top_max do
					data[ivm] = top
					ivm = ivm + ystride
				end
			end

			if river_here then
				data[ivm] = c_rwater
				ivm = ivm + ystride
			elseif node_deco and h >= offset_y then
				data[ivm] = node_deco
			end

			if h < offset_y then
				for y = math.max(h+1, minp.y), math.min(offset_y, maxp.y) do
					data[ivm] = c_water
					ivm = ivm + ystride
				end
			end
		end
	end
	end

	vm:set_data(data)
	for _, params in ipairs(schems_to_generate) do
		minetest.place_schematic_on_vmanip(vm, params.pos, params.schem, "random", nil, false) -- Place schematics
	end
	vm:set_lighting({day = 0, night = 0})
	vm:calc_lighting()
	vm:update_liquids()
	vm:write_to_map()

	-- Decrease delay, remove chunks from cache when time is over
	for _, layer_delays in ipairs(delays) do
		for n, delay in pairs(layer_delays) do
			if n ~= "data" then -- avoid the "data" field!
				if delay <= 1 then
					layer_delays[n] = nil
					layer_delays.data[n] = nil -- layer_delays.data is the layer itself
					print("[geo_mapgen]   Uncaching chunk " .. n)
				else
					layer_delays[n] = delay - 1
				end
			end
		end
	end

	local t3 = os.clock()
	local time = t3 - t0
	print("[geo_mapgen] Mapgen finished in " .. displaytime(time))

	mapgens = mapgens + 1
	time_sum = time_sum + time
	time_sum2 = time_sum2 + time ^ 2
end)

if projlib and proj then
	local wgs84 = "wgs84 +degrees"
	local project = projlib:new(wgs84, proj)
	local unproject = project:reverse()

	local game_to_proj = game_to_map:combine(map_to_proj)
	local proj_to_game = game_to_proj:reverse()

	local function get_rw_coords(pos)
		return unproject(game_to_proj(pos.x, pos.z))
	end

	local function get_game_pos(lon, lat)
		return proj_to_game(project(lon, lat))
	end

	local function display_dms(angle)
		local degree, rem = math.modf(angle)
		local minute, rem = math.modf(math.abs(rem)*60)
		local second = math.floor(rem*60)
		return ("%d°%02u'%02u\""):format(degree, minute, second)
	end

	minetest.register_chatcommand("rwpos", {
		params = "",
		description = "Get your real-world position in latitude/longitude",
		func = function(name)
			local player = minetest.get_player_by_name(name)
			local pos = player:getpos()
			local lon, lat = get_rw_coords(pos)
			local latdir = lat > 0 and 'N' or 'S'
			local londir = lon > 0 and 'E' or 'W'
			return true, ("%s%s, %s%s"):format(display_dms(math.abs(lat)), latdir, display_dms(math.abs(lon)), londir)
		end,
	})

	local function parse_coordinate(cstr)
		if tonumber(cstr) then
			return tonumber(cstr)
		end
		local deg, min, sec = cstr:match("^(-?[%d.]+)°?([%d.]*)'?([%d.]*)\"?$")
		return tonumber(deg) + (tonumber(min) or 0)/60 + (tonumber(sec) or 0)/3600
	end

	minetest.register_chatcommand("rwtp", {
		params = "<lat> <lon>",
		privs = {teleport=true},
		description = "Teleport to a real-world position in latitude/longitude",
		func = function(name, param)
			local player = minetest.get_player_by_name(name)
			local latdir1, latdeg, latmin, latsec, latdir2, londir1, londeg, lonmin, lonsec, londir2 = param:gsub("°", "~"):match("^([NS]?)%s*(-?[%d.]+).?([%d.]*).?([%d.]*)[^,%sNS]?([NS]?)[,%s]%s*([EW]?)%s*(-?[%d.]+).?([%d.]*).?([%d.]*)[^,%sEW]?([EW]?)$")

			if not (latdeg and londeg) then
				return false, "Invalid coordinates"
			end
			latdeg, londeg = tonumber(latdeg), tonumber(londeg)
			if not (latdeg and londeg) then
				return false, "Invalid coordinates"
			end
			
			local latdir, londir = 1, 1
			if latdir1 == 'S' or latdir2 == 'S' then
				latdir = -1
			end
			if londir1 == 'W' or londir2 == 'W' then
				londir = -1
			end
			if latdeg < 0 then
				latdir = -latdir
				latdeg = -latdeg
			end
			if londeg < 0 then
				londir = -londir
				londeg = -londeg
			end
			
			local lat = latdir * (latdeg + (tonumber(latmin) or 0)/60 + (tonumber(latsec) or 0)/3600)
			local lon = londir * (londeg + (tonumber(lonmin) or 0)/60 + (tonumber(lonsec) or 0)/3600)

			local x, z = get_game_pos(lon, lat)
			player:setpos({x=x, y=0, z=z})
			return true, ("Teleported at %f %f"):format(lat, lon)
		end,
	})
end			

minetest.register_on_shutdown(function()
	print("[geo_mapgen] Mapgen calls: " .. mapgens)
	local average = time_sum / mapgens
	print("[geo_mapgen] Average time: " .. displaytime(average))
	local stdev = math.sqrt(time_sum2 / mapgens - average ^ 2)
	print("[geo_mapgen] Standard dev: " .. displaytime(stdev))
end)
