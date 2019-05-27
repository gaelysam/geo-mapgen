local numberio = {}

-- Define number types

local ntypes = {
	int8    = {1, false, true},
	uint8   = {1, false, false},
	int16   = {2, false, true},
	uint16  = {2, false, false},
	float16 = {2, true, 5, 10},
	int32   = {4, false, true},
	uint32  = {4, false, false},
	float32 = {4, true, 8, 23},
	int64   = {8, false, true},
	uint64  = {8, false, false},
	float64 = {8, true, 11, 52},
}

for name, ntype in pairs(ntypes) do
	numberio[name] = ntype
end

-- Endianness

local bigendian = false

function numberio.get_endianness()
	return bigendian
end

function numberio.set_endianness(is_bigendian)
	bigendian = is_bigendian
end

local function reverse_table(t)
	local n = #t
	for i=1, math.floor(n/2) do
		t[i], t[n+1-i] = t[n+1-i], t[i]
	end
end

-- READ NUMBERS

local function read_bits(bytes, ...)
	local pattern = {...}
	if not bigendian then
		reverse_table(bytes)
	end
	local r = 8
	local b = table.remove(bytes, 1)
	local v = {}
	for _, nbits in ipairs(pattern) do
		local n = 0
		while nbits > r do
			nbits = nbits - r
			n = n + b*2^nbits
			r = 8
			b = table.remove(bytes, 1)
		end
		if nbits > 0 then
			local d = 2^(r-nbits)
			n = n + math.floor(b/d)
			b = b % d
			r = r - nbits
		end
		table.insert(v, n)
	end

	return unpack(v)
end

local function get_reader(ntype)
	local len, is_float, p1, p2 = unpack(ntype)

	local reader
	if is_float then -- Float
		local exp_offset = -2^(p1-1)+1
		local exp_max = 2^p1-1
		local denormal_factor = 2^(exp_offset+1)
		local mantissa_factor = 2^-p2
		reader = function(input)
			local sign, exp, mantissa = read_bits(input, 1, p1, p2)
			sign = (-1)^sign
			if exp == 0 then
				if mantissa == 0 then
					return sign * 0
				end
				return sign * denormal_factor * mantissa * mantissa_factor
			elseif exp == exp_max then
				if mantissa == 0 then
					return sign*math.huge
				else
					return sign < 0 and math.sqrt(-1) or -math.sqrt(-1)
				end
			end
			return sign * 2^(exp+exp_offset) * (1 + mantissa*mantissa_factor)
		end
	elseif p1 then -- Signed int
		local nbits = len*8
		local max = 2^(nbits-1)
		local decr = 2^nbits
		reader = function(input)
			local n = read_bits(input, nbits)
			if n >= max then
				return n - decr
			end
			return n
		end
	else -- Unsigned int
		local nbits = len*8
		reader = function(input)
			return read_bits(input, nbits)
		end
	end
	ntype.reader = reader
	return reader
end

function numberio.readnumber(input, ntype)
	if type(ntype) == "string" then
		ntype = ntypes[ntype]
	end
	local reader = ntype.reader
	if not reader then
		reader = get_reader(ntype)
	end

	local len = ntype[1]
	local inputlen = math.floor(#input/len)

	if inputlen == 1 then
		local bytes = {input:byte(1, len)}
		return reader(bytes)
	else
		local v = {}
		local start = 1
		for i=1, inputlen do
			local stop = i*len
			local bytes = {input:byte(start, stop)}
			table.insert(v, reader(bytes))
			start = stop + 1
		end

		return unpack(v)
	end
end

return numberio
