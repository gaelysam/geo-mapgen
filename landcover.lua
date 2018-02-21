-- System taken from my old 30-biomes mod: https://github.com/Gael-de-Sailly/30-biomes/blob/master/init.lua

local path = minetest.get_modpath(minetest.get_current_modname())
local biomepath = path .. "/biomes.csv"
local decopath = path .. "/decorations.csv"

local read_csv = dofile(path .. "/csv.lua")

local biomelist = read_csv(biomepath)

local function repack(name, stone, fill, top, ...)
	return name, stone, fill, top, {...}
end

local id = minetest.get_content_id

local biomes = {}
for _, biome_raw in ipairs(biomelist) do
	local biome = {}
	local name, stone, fill, top, decos = repack(unpack(biome_raw)) -- Unpack the 4 first arguments but leave the following packed.
	if top and #top > 0 then
		top = top:split("%s", false, 1, true)
		biome.top = id(top[1])
		biome.top_depth = tonumber(fill[2] or 1)
	else
		biome.top_depth = 0
	end
	if fill and #fill > 0 then
		fill = fill:split("%s", false, 1, true)
		biome.filler = id(fill[1])
		biome.filler_depth = tonumber(fill[2] or 1) + biome.top_depth -- Depth is cumulative
	else
		biome.filler_depth = biome.top_depth
	end
	if stone and #stone > 0 then
		biome.stone = id(stone)
	end

	biomes[name] = biome
end

return biomes
