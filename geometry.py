def transform(gt, pos):
	a,b,c,d,e,f = gt
	px, py = pos[0], pos[1]
	x = a + b*px + c*py
	y = d + e*px + f*py
	return x, y

def inverse(gt, pos):
	a,b,c,d,e,f = gt
	x, y = pos[0], pos[1]
	if c == 0:
		px = (x-a) / b
		py = (y-d-e*px) / f
	elif e == 0:
		py = (y-d) / f
		px = (x-a-c*py) / b
	elif b == 0:
		py = (x-a) / c
		px = (y-d-f*py) / e
	elif f == 0:
		px = (y-d) / e
		py = (x-a-b*px) / c
	else:
		px = ((y-d)/f+(a-x)/c) / (e/f-b/c)
		py = (x-a-b*px) / c
	return px, py
