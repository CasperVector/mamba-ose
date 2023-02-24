import time
import numpy
import threading
from ophyd import select_version, Component, AreaDetector, HDF5Plugin
from ophyd.device import BlueskyInterface, Staged
from ophyd.signal import EpicsSignalRO, EpicsSignal
from ophyd.areadetector.base import ADBase, ADComponent, EpicsSignalWithRBV
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.filestore_mixins import \
	FileStoreHDF5, FileStoreIterativeWrite
from ophyd.areadetector.trigger_mixins import ADTriggerStatus
from ophyd.utils.errors import UnprimedPlugin

MyHDF5Plugin = select_version(HDF5Plugin, (3, 15))

class MyTriggerBase(BlueskyInterface):
	_status_type = ADTriggerStatus

	def __init__(self, *args, image_name = None, **kwargs):
		super().__init__(*args, **kwargs)
		if image_name is None:
			image_name = "_".join([self.name, "image"])
		self._image_name, self._datum_keys = image_name, [image_name]

class SoftTrigger(MyTriggerBase):
	_acquisition_signal, _counter_signal, _status = "cam.acquire", None, None

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if self._acquisition_signal:
			self._acquisition_signal = getattr(self, self._acquisition_signal)
		if self._counter_signal:
			self._counter_signal = getattr(self, self._counter_signal)
		self.stage_sigs.update([("cam.acquire",
			0 if self._acquisition_signal == self.cam.acquire else 1)])

	def stage(self):
		(self._counter_signal or self._acquisition_signal)\
			.subscribe(self._acquire_changed)
		super().stage()

	def unstage(self):
		super().unstage()
		(self._counter_signal or self._acquisition_signal)\
			.clear_sub(self._acquire_changed)

	def trigger(self):
		assert self._staged == Staged.yes
		self._status = self._status_type(self)
		self._acquisition_signal.put(1)
		self.dispatch(self._image_name, time.time())
		return self._status

	def _acquire_changed(self, value, old_value, **kwargs):
		if self._status is None:
			return
		if self._counter_signal or (old_value == 1 and value == 0):
			status, self._status = self._status, None
			status.set_finished()

class DxpTrigger(MyTriggerBase):
	def wait_finish(self):
		self.cam.erase_start.put(1)
		if not self.cam.wait_acquiring(True):
			raise TimeoutError\
				("Timeout waiting for %r to be high" % self.cam.acquiring)
		time.sleep(self.cam.preset_real.get())
		self.cam.next_pixel.put(1)
		if not self.cam.wait_acquiring(False):
			self.cam.stop_all.put(1)
			raise TimeoutError\
				("Timeout waiting for %r to be low" % self.cam.acquiring)

	def trigger(self):
		assert self._staged == Staged.yes
		status = self._status_type(self)
		self.dispatch(self._image_name, time.time())
		def wait():
			try:
				self.wait_finish()
			except Exception as exc:
				status.set_exception(exc)
				raise
			status.set_finished()
		threading.Thread(target = wait, daemon = True).start()
		return status

class CptHDF5(MyHDF5Plugin, FileStoreHDF5, FileStoreIterativeWrite):
	get_frames_per_point = lambda self: self.parent.cam.num_images.get()

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.filestore_spec = "AD_HDF5_SWMR"

	def warmup(self):
		self.enable.set(1).wait()
		self.swmr_mode.set(1).wait()

class CptHDF5Dxp(CptHDF5):
	get_frames_per_point = lambda self: 1

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

class DxpCam(ADBase):
	_default_configuration_attrs = ADBase._default_configuration_attrs + (
		"collect_mode", "ignore_gate", "input_logic_polarity",
		"pixel_advance_mode", "pixels_per_run", "pixels_per_buffer",
		"auto_pixels_per_buffer", "preset_mode", "preset_real"
	)

	collect_mode = ADComponent(EpicsSignalWithRBV, "CollectMode")
	ignore_gate = ADComponent(EpicsSignalWithRBV, "IgnoreGate")
	input_logic_polarity = ADComponent(EpicsSignalWithRBV, "InputLogicPolarity")
	pixel_advance_mode = ADComponent(EpicsSignalWithRBV, "PixelAdvanceMode")
	pixels_per_run = ADComponent(EpicsSignalWithRBV, "PixelsPerRun")
	pixels_per_buffer = ADComponent(EpicsSignalWithRBV, "PixelsPerBuffer")
	auto_pixels_per_buffer = \
		ADComponent(EpicsSignalWithRBV, "AutoPixelsPerBuffer")
	preset_mode = ADComponent(EpicsSignal, "PresetMode")
	preset_real = ADComponent(EpicsSignal, "PresetReal")
	erase_start = ADComponent(EpicsSignal, "EraseStart")
	stop_all = ADComponent(EpicsSignal, "StopAll")
	next_pixel = ADComponent(EpicsSignal, "NextPixel")
	acquiring = ADComponent(EpicsSignal, "Acquiring")

	def wait_acquiring(self, val):
		for i in range(100):
			if bool(self.acquiring.get()) == bool(val):
				return True
			time.sleep(0.1)
		else:
			return False

	def warmup(self):
		self.erase_start.put(1)
		self.wait_acquiring(True)
		self.next_pixel.put(1)
		self.wait_acquiring(False)
		self.stop_all.put(1)

class SitoroCam(DxpCam):
	_default_configuration_attrs = \
		DxpCam._default_configuration_attrs + ("ndarray_mode",)
	ndarray_mode = ADComponent(EpicsSignalWithRBV, "NDArrayMode")

def make_detector(name, inherit = None, **kwargs):
	if not inherit:
		inherit = (SoftTrigger, AreaDetector)
	def warmup(obj):
		obj.hdf1.warmup()
		obj.cam.warmup()
		if not sum(obj.hdf1.array_size.get()):
			raise UnprimedPlugin("%s failed to warm up" % obj.hdf1.vname())
	attrs = {
		"_default_read_attrs": ["hdf1"],
		"cam": Component(MyCam, "cam1:"),
		"hdf1": Component(CptHDF5, "HDF1:", write_path_template = "/"),
		"warmup": warmup
	}
	attrs.update(kwargs)
	return type(name, inherit, attrs)

MyAreaDetector = make_detector("MyAreaDetector")
DxpDetector, SitoroDetector = [make_detector(
	name, (DxpTrigger, AreaDetector), cam = Component(cam, ""),
	hdf1 = Component(CptHDF5Dxp, "HDF1:", write_path_template = "/")
) for name, cam in [("DxpDetector", DxpCam), ("SitoroDetector", SitoroCam)]]

