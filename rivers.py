from heapq import heappush, heappop, heapify
import sys
import numpy as np
sys.setrecursionlimit(65536)

def generate_rivermap(heightmap, sea_level=128, river_limit=1000, max_river_hdiff=40, river_power=0.25):
	print("[rivers]: Finding start points")

	(Y, X) = heightmap.shape
	visited = np.zeros((Y,X), dtype=bool)

	start_points = []

	def add_start_point(y,x):
		start_points.append((heightmap[y, x] + np.random.random(), y, x))
		visited[y, x] = True

	def find_start_points(t, x=1, y=1):
		sy, sx = t.shape
		if t.all() or not t.any():
			return
		if max(sx, sy) == 3:
			if (not t[1,1]) and (t[0,1] or t[1,0] or t[1,2] or t[2,1]):
				add_start_point(y,x)
			return
		if sx < sy:
			cut = sy//2
			find_start_points(t[:cut+1,:], x=x, y=y)
			find_start_points(t[cut-1:,:], x=x, y=y+cut-1)
		else:
			cut = sx//2
			find_start_points(t[:,:cut+1], x=x, y=y)
			find_start_points(t[:,cut-1:], x=x+cut-1, y=y)

	seas = heightmap <= sea_level
	find_start_points(seas)

	to_explore = X * Y - np.count_nonzero(seas)

	for x in np.flatnonzero(~seas[0,:]):
		add_start_point(0, x)
	for x in np.flatnonzero(~seas[-1,:]):
		add_start_point(Y-1, x)
	for y in np.flatnonzero(~seas[1:-1,0]):
		add_start_point(y+1, 0)
	for y in np.flatnonzero(~seas[1:-1,-1]):
		add_start_point(y+1, X-1)

	del seas

	print("Found", str(len(start_points)), "start points")

	heap = start_points[:]
	heapify(heap)

	print("Building river trees:", str(to_explore), "points to visit")

	flow_dirs = np.zeros((Y, X), dtype=np.int8)

	# Directions:
	#	1: +x
	#	2: +y
	#	4: -x
	#	8: -y

	def try_push(y, x): # try_push does 2 things at once: returning whether water can flow, and push the upward position in heap if yes.
		if not visited[y, x]:
			h = heightmap[y, x]
			if h > sea_level:
				heappush(heap, (h + np.random.random(), y, x))
				visited[y, x] = True
				return True
		return False

	def process_neighbors(y, x):
		dirs = 0
		if x > 0 and try_push(y, x-1):
			dirs+= 1
		if y > 0 and try_push(y-1, x):
			dirs += 2
		if x < X-1 and try_push(y, x+1):
			dirs += 4
		if y < Y-1 and try_push(y+1, x):
			dirs += 8
		flow_dirs[y, x] = dirs

	while len(heap) > 0:
		t = heappop(heap)
		to_explore -= 1
		if to_explore % 1000000 == 0:
			print(str(to_explore // 1000000), "× 10⁶ points remaining", "Altitude:", int(t[0]), "Queue:", len(heap))
		process_neighbors(t[1], t[2])

	visited = None

	print("Calculating water quantity")

	waterq = np.ones((Y, X))
	river_array = np.zeros((Y, X), dtype=bool)

	def draw_river(x, y, q):
		if q >= river_limit:
			rsize = int((q / river_limit)**river_power)
			if rsize > 1:
				hmax = heightmap[y,x] + max_river_hdiff
				rsize -= 1
				xmin = max(x-rsize, 0)
				xmax = min(x+rsize+1, X)
				ymin = max(y-rsize, 0)
				ymax = min(y+rsize+1,Y)
				river_array[y,xmin:xmax] += heightmap[y,xmin:xmax] <= hmax
				river_array[ymin:ymax,x] += heightmap[ymin:ymax,x] <= hmax
			else:
				river_array[y,x] = True

	def set_water(y, x):
		water = 1
		dirs = flow_dirs[y, x]

		if dirs % 2 == 1:
			water += set_water(y, x-1)
		dirs //= 2
		if dirs % 2 == 1:
			water += set_water(y-1, x)
		dirs //= 2
		if dirs % 2 == 1:
			water += set_water(y, x+1)
		dirs //= 2
		if dirs % 2 == 1:
			water += set_water(y+1, x)
		waterq[y, x] = water

		if water >= river_limit:
			draw_river(x, y, water)
		return water

	maxwater = 0
	for start in start_points:
		water = set_water(start[1], start[2])
		if water > maxwater:
			maxwater = water

	print("Maximal water quantity:", str(maxwater))

	flow_dirs = None

	return river_array
