import numpy as np
import database as db

class Landcover(db.Layer):
	def __init__(self, dataset, legend=None, **kwargs):
		db.Layer.__init__(self, dataset, **kwargs)
		self.type = 2
		self.lctable = None
		if legend is not None:
			self.set_legend(legend)

	def set_legend(self, legend):
		if isinstance(legend, str):
			table_raw = np.loadtxt(legend, dtype=[('i', 'u1'), ('biome', 'U64')])
		else:
			table_raw = legend
		table_full = np.zeros(256, dtype='U64')
		table_full[table_raw['i']] = table_raw['biome']

		existing_biomes = np.unique(table_raw['biome']).tolist()

		transform_table = np.zeros(256, dtype='u1')
		for i in range(256):
			if len(table_full[i]) > 0:
				transform_table[i] = existing_biomes.index(table_full[i])+1

		self.lctable = transform_table
		self.metadata = ','.join(existing_biomes)

	def on_array_save(self, array):
		return self.lctable[array]
