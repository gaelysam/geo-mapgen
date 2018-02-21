-- System taken from my old 30-biomes mod: https://github.com/Gael-de-Sailly/30-biomes/blob/master/init.lua

local path = minetest.get_modpath(minetest.get_current_modname())
local biomepath = path .. "/biomes.csv"
local decopath = path .. "/decorations.csv"

local read_csv = dofile(path .. "/csv.lua")

local biomelist = read_csv(biomepath)
local decolist = read_csv(decopath)

local function repack3rd(p1, p2, ...)
	return p1, p2, {...}
end

local function repack5th(p1, p2, p3, p4, ...)
	return p1, p2, p3, p4, {...}
end

local id = minetest.get_content_id

local decos = {}
for _, deco_raw in ipairs(decolist) do
	local deco = {}
	local name, decotype, list = repack3rd(unpack(deco_raw))
	local is_schem = false
	local itemlist = {}
	if decotype == "schem" then
		is_schem = true
		for n, item in ipairs(list) do
			print(item)
			if #item > 0 then
				if item:sub(1,1) == "@" then
					local slash_pos = item:find("%/")
					local modname = item:sub(2,slash_pos-1)
					print(modname)
					item = minetest.get_modpath(modname) .. item:sub(slash_pos,-1)
				end
				itemlist[n] = item
			end
		end
	elseif decotype == "node" then
		for n, item in ipairs(list) do
			if #item > 0 then
				print(item)
				itemlist[n] = id(item)
			end
		end
	end
	deco.list = itemlist
	deco.is_schem = is_schem

	decos[name] = deco
end

local biomes = {}
for _, biome_raw in ipairs(biomelist) do
	local biome = {}
	local name, stone, fill, top, biome_decos = repack5th(unpack(biome_raw)) -- Unpack the 4 first arguments but leave the following packed.
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

	biome.decos = {}
	for _, deco in ipairs(biome_decos) do
		if #deco > 0 then
			deconame, prob = unpack(deco:split(":", false))
			table.insert(biome.decos, {prob=tonumber(prob), deco=decos[deconame]})
		end
	end

	biomes[name] = biome
end

return biomes
