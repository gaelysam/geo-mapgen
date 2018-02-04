local path = "heightmap.dat"
local conf_path = "heightmap.dat.conf"

file = io.open(minetest.get_worldpath() .. "/" .. path)
local conf = Settings(minetest.get_worldpath() .. "/" .. conf_path)

local scale = conf:get("scale") or 40
local remove_delay = 10 -- Number of mapgen calls until a chunk is unloaded

local function parse(str, signed) -- little endian
	local bytes = {str:byte(1, -1)}
	local n = 0
	local byte_val = 1
	for _, byte in ipairs(bytes) do
		n = n + (byte * byte_val)
		byte_val = byte_val * 256
	end
	if signed and n >= byte_val / 2 then
		return n - byte_val
	end
	return n
end

if file:read(5) ~= "GEOMG" then
	print('[geo_mapgen] WARNING: file may not be in the appropriate format. Signature "GEOMG" not recognized.')
end

local version = parse(file:read(1))

-- Geometry stuff
local frag = parse(file:read(2))
local X = parse(file:read(2))
local Z = parse(file:read(2))
local chunks_x = math.ceil(X / frag) -- Number of chunks along X axis
local chunks_z = math.ceil(Z / frag) -- Number of chunks along Z axis

local last_chunk_length = (X-1) % frag + 1 -- Needed for incrementing index because last chunk may be truncated in length and therefore need an unusual increment

local function displaytime(time)
	return math.floor(time * 1000000 + 0.5) / 1000 .. " ms"
end

local with_time = false
local timer_prepare, timer_noise, timer_data, timer_write, timer_cleaning, timer_total
if TimeStats then
	timer_prepare = TimeStats("Mapgen preparation", true)
	timer_load = TimeStats("Chunks loading", true)
	timer_data = TimeStats("Data collecting", true)
	timer_write = TimeStats("Data writing", true)
	timer_cleaning = TimeStats("Cleaning chunks", true)
	timer_total = TimeStats("Mapgen", true)
	with_time = true
end

-- Metatables
local function load_chunk(layer, n)
	if with_time then
		timer_load:resume()
	end

	local index = layer.index
	local address_min = index[n-1] -- inclusive
	local address_max = index[n] -- exclusive
	local count = address_max - address_min
	file:seek("set", layer.offset + address_min)
	local data_raw = minetest.decompress(file:read(count))
	layer[n] = data_raw -- Put raw data in table
	layer.delay[n] = remove_delay -- Set delay for this chunk
	
	if with_time then
		timer_load:pause()
	end
	return data_raw
end

local mt = {__index = load_chunk} -- Metatable that will allow to load chunks on request

local delays = {} -- Will be a list of delay tables. A delay table is a table that contains the delay before unload of every loaded chunk.

local heightmap = nil
local rivermap = nil
local rivers = false

-- Layers
local layers = {}
local layer_count = parse(file:read(1))
for l=1, layer_count do
	local datatype = parse(file:read(1)) -- Type of data: 0 = heightmap, 1 = rivermap
	local itemsize_raw = parse(file:read(1))
	local signed = false
	local itemsize = itemsize_raw
	if itemsize >= 16 then
		signed = true
		itemsize = itemsize_raw - 16
	end

	local index_length = parse(file:read(4))
	local meta = ""
	if version >= 1 then
		local meta_length = parse(file:read(2))
		meta = file:read(meta_length)
	end

	local index_raw = minetest.decompress(file:read(index_length))
	local index = {[0] = 0} -- Variable is called index instead of table to avoid name conflicts. Will contain a list of the ending position for every chunk, begin at chunk 1, so (unexisting) chunk 0 would end at pos 0. This makes simpler the calculation of chunk size that is index[i] - index[i-1] even for i=1.
	for i=1, #index_raw / 4 do
		index[i] = parse(index_raw:sub(i*4-3, i*4))
	end

	local delay = {} -- Delay table, will contain the number of mapgen calls before unloading, for every loaded chunk
	delays[l] = delay

	local layer = {
		delay = delay,
		offset = file:seek(), -- Position of first data
		itemsize = itemsize,
		signed = signed,
		index = index,
		meta = meta,
	}

	delay.data = layer -- Reference layer in delay table

	setmetatable(layer, mt)

	if datatype == 0 then -- Code for heightmap
		heightmap = layer
	elseif datatype == 1 then
		print("Rivermap enabled!")
		rivermap = layer
		rivers = true
	end

	local data_size = index[#index]
	file:seek("cur", data_size) -- Skip data and go to the position of the next layer
end

local data = {}

minetest.register_on_mapgen_init(function(mgparams)
	minetest.set_mapgen_params({mgname="singlenode", flags="nolight"})
end)

-- Decode the value of a chunk for a given pixel
local function value(layer, nchunk, n)
	local itemsize = layer.itemsize
	return parse(layer[nchunk]:sub((n-1)*itemsize + 1, n*itemsize), layer.signed)
end

minetest.register_on_generated(function(minp, maxp, seed)
	print("[geo_mapgen] Generating from " .. minetest.pos_to_string(minp) .. " to " .. minetest.pos_to_string(maxp))
	if with_time then
		timer_total:start()
		timer_prepare:start()
		timer_load:start(false)
	end

	local c_stone = minetest.get_content_id("default:stone")
	local c_dirt = minetest.get_content_id("default:dirt")
	local c_lawn = minetest.get_content_id("default:dirt_with_grass")
	local c_water = minetest.get_content_id("default:water_source")
	local c_rwater = minetest.get_content_id("default:river_water_source")

	local xmin = math.max(minp.x, 0)
	local xmax = math.min(maxp.x, X-1)
	local zmin = math.max(minp.z, -Z+1) -- Reverse Z coordinates
	local zmax = math.min(maxp.z, 0)

	local vm, emin, emax = minetest.get_mapgen_object("voxelmanip")
	vm:get_data(data)
	local a = VoxelArea:new({MinEdge = emin, MaxEdge = emax})
	local ystride = a.ystride

	if with_time then
		timer_prepare:stop()
		timer_data:start()
	end

	for x = xmin, xmax do
	for z = zmin, zmax do
		local ivm = a:index(x, minp.y, z)

		local xchunk = math.floor(x / frag)
		local zchunk = math.floor(-z / frag)
		local nchunk = xchunk + zchunk * chunks_x + 1
		
		local increment = frag
		if xchunk + 1 == chunks_x then -- Last chunk of the line: may be truncated, that would change the line increment.
			increment = last_chunk_length
		end
		local xpx = x % frag
		local zpx = -z % frag
		local npx = xpx + zpx * increment + 1 -- Increment is used here

		local h = math.floor(value(heightmap, nchunk, npx) / scale)

		local river_here = false
		if rivers then
			river_here = value(rivermap, nchunk, npx) > 0
		end

		for y = minp.y, math.min(math.max(h, 0), maxp.y) do
			local node
			if h - y < 3 then
				if h == y and y >= 0 then
					if river_here then
						node = c_rwater
					else
						node = c_lawn
					end
				elseif y > h then
					node = c_water
				else
					node = c_dirt
				end
			else
				node = c_stone
			end
			data[ivm] = node
			ivm = ivm + ystride
		end
	end
	end

	if with_time then
		timer_data:stop()
		timer_write:start()
	end

	vm:set_data(data)
	vm:set_lighting({day = 0, night = 0})
	vm:calc_lighting()
	vm:update_liquids()
	vm:write_to_map()

	if with_time then
		timer_write:stop()
		timer_cleaning:start()
	end

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

	if with_time then
		timer_cleaning:stop()
		timer_load:stop()
		timer_total:stop()
	end
end)
