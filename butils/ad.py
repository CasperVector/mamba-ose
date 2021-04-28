import time
from ophyd import select_version, Component, \
	AreaDetector, HDF5Plugin, SingleTrigger
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.filestore_mixins import \
	FileStoreHDF5, FileStoreIterativeWrite

MyHDF5Plugin = select_version(HDF5Plugin, (3, 15))

class CptHDF5(MyHDF5Plugin, FileStoreHDF5, FileStoreIterativeWrite):

	get_frames_per_point = lambda self: self.parent.cam.num_images.get()

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.filestore_spec = "AD_HDF5_SWMR"

	def warmup(self):
		self.enable.set(1).wait()
		self.swmr_mode.set(1).wait()

class MyCam(AreaDetectorCam):
	def warmup(self, sleep = 2.0):
		sigs = [(self.array_callbacks, 1), (self.acquire, 1)]
		orig_vals = [(sig, sig.get()) for sig, val in sigs]

		for sig, val in sigs:
			time.sleep(0.1)
			sig.put(val)
		if sleep > 0:
			time.sleep(sleep)
		else:
			for i in range(100):
				if not self.acquire.get():
					break
				time.sleep(0.1)
		for sig, val in reversed(orig_vals):
			sig.set(val).wait()

class MyAreaDetector(SingleTrigger, AreaDetector):
	_default_read_attrs = ["hdf1"]
	cam = Component(MyCam, "cam1:")
	hdf1 = Component(CptHDF5, "HDF1:", write_path_template = "/")
	def warmup(self):
		self.hdf1.warmup()
		self.cam.warmup()

