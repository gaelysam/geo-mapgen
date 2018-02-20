import numpy as np

index_dtype = np.dtype([("i", "u1"), ("biome", "U64")])
def make_landcover(datamap, index_file):
	index_raw = np.loadtxt(index_file, dtype=index_dtype)
	index_full = np.zeros(256, dtype=np.dtype("U64"))
	index_full[index_raw["i"]] = index_raw["biome"]
	values = np.unique(datamap)

	bdict = {}
	blist = []
	num_index = np.zeros(256, dtype=np.dtype("u1"))
	i = 1
	for value in values:
		biome = index_full[value]
		if biome == '':
			continue

		if biome in bdict:
			num_index[value] = bdict[biome]
		else:
			bdict[biome] = i
			blist.append(biome)
			num_index[value] = i
			i += 1
	return num_index[datamap], ','.join(blist)
