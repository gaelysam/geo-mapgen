local gt_mt = {}

local function geotransform(a, b, c, d, e, f)
	local gt = type(a) == "table" and a or {a,b,c,d,e,f} -- Allows both a table or 6 parameters
	return setmetatable(gt, gt_mt)
end

local function apply(gt, x, y)
	return gt[1]+x*gt[2]+y*gt[3], gt[4]+x*gt[5]+y*gt[6]
end

local function reverse(gt)
	local a, b, c, d, e, f = unpack(gt)
	local det = 1/(b*f-e*c)
	return geotransform((c*d-a*f)*det, f*det, -c*det, (a*e-b*d)*det, -e*det, b*det)
end

local function combine(gt1, gt2)
	local a1, b1, c1, d1, e1, f1 = unpack(gt1)
	local a2, b2, c2, d2, e2, f2 = unpack(gt2)
	return geotransform(
		a2+a1*b2+d1*c2,
		b1*b2+e1*c2,
		c1*b2+f1*c2,
		d2+a1*e2+d1*f2,
		b1*e2+e1*f2,
		c1*e2+f1*f2
	)
end

gt_mt.apply = apply
gt_mt.reverse = reverse
gt_mt.combine = combine
gt_mt.__call = apply
gt_mt.__index = gt_mt

return geotransform
