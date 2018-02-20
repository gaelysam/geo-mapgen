local function read_csv(path)
	local file = io.open(path, "r")
	local t = {}
	for line in file:lines() do
		if line:sub(1,1) ~= "#" and line:find("[^%,% ]") then
			table.insert(t, line:split(",", true))
		end
	end
	return t
end

return read_csv
