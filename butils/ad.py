import time
import numpy
import threading
from ophyd import select_version, Component, EpicsSignalRO, \
    EpicsSignal, ADBase, ADComponent, EpicsSignalWithRBV, \
    DetectorBase, CamBase, HDF5Plugin, ADTriggerStatus
from ophyd.device import BlueskyInterface, Staged
from ophyd.signal import AttributeSignal
from ophyd.areadetector.plugins import PluginBase
from ophyd.areadetector.filestore_mixins import \
    FileStoreHDF5, FileStoreIterativeWrite
from ophyd.utils.errors import UnprimedPlugin
from .ophyd import ThrottleMonitor

MyHDF5Plugin = select_version(HDF5Plugin, (3, 15))

class MyTriggerBase(BlueskyInterface):
    _status_type = ADTriggerStatus

    def __init__(self, *args, image_name = None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = "_".join([self.name, "image"])
        self._image_name, self._datum_keys = image_name, [image_name]

class SoftTrigger(MyTriggerBase):
    _acquisition_signal = "cam.acquire"
    _counter_signal = _orig_acquire = _status = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._acquisition_signal:
            self._acquisition_signal = getattr(self, self._acquisition_signal)
        if self._counter_signal:
            self._counter_signal = getattr(self, self._counter_signal)
        self.stage_sigs.update([("cam.acquire",
            0 if self._acquisition_signal == self.cam.acquire else 1)])

    def stage(self):
        self._orig_acquire = self.cam.acquire.get()
        if self._orig_acquire == self.stage_sigs["cam.acquire"] == 1:
            self.cam.acquire.put(0)
        (self._counter_signal or self._acquisition_signal)\
            .subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        super().unstage()
        (self._counter_signal or self._acquisition_signal)\
            .clear_sub(self._acquire_changed)
        if self._orig_acquire == self.stage_sigs["cam.acquire"] == 1:
            self.cam.acquire.put(1)

    def trigger(self):
        assert self._staged == Staged.yes
        self._status = self._status_type(self)
        self._acquisition_signal.put(1)
        self.dispatch(self._image_name, time.time())
        return self._status

    def _acquire_changed(self, *, value, old_value, **kwargs):
        if self._status is None:
            return
        if (self._counter_signal and value) or (old_value == 1 and value == 0):
            status, self._status = self._status, None
            status.set_finished()

class DxpTrigger(MyTriggerBase):
    def wait_finish(self):
        self.cam.erase_start.put(1)
        time.sleep(self.cam.preset_real.get())
        for i in range(100):
            if not self.cam.acquiring.get():
                break
            time.sleep(0.02)
        else:
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

class DxpDetectorBase(DetectorBase):
    make_data_key = lambda self: dict(
        shape = (1,) + tuple(self.hdf1.array_size.get())[-2:],
        source = "PV." + self.prefix, dtype = "array", external = "FILESTORE:"
    )

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

class MyImagePlugin(ThrottleMonitor, PluginBase):
    _plugin_type = "NDPluginStdArrays"
    array_data = Component(EpicsSignalRO, "ArrayData", auto_monitor = True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disable_on_stage()
        self.ensure_nonblocking()

    def monitor(self, dnotify):
        image_name, _timestamp = self.parent._image_name, [0.0]
        def cb(*, value, timestamp, **kwargs):
            if value is None or not self.maybe_monitor(_timestamp, timestamp):
                return
            shape = list(self.array_size.get())
            while True:
                if not shape:
                    return
                if all(shape):
                    break
                shape.pop(0)
            dnotify("monitor/image", {
                "data": {image_name: value[:numpy.prod(shape)].reshape(shape)},
                "timestamps": {image_name: timestamp}
            })
        return self.array_data.subscribe(cb, run = False)

class MyCam(CamBase):
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

    port_name = ADComponent(EpicsSignalRO, "Asyn.PORT", string = True)
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

    def warmup(self):
        self.erase_start.put(1)
        time.sleep(min(2.0, self.preset_real.get()))
        self.stop_all.put(1)

class SitoroCam(DxpCam):
    _default_configuration_attrs = \
        DxpCam._default_configuration_attrs + ("ndarray_mode",)
    ndarray_mode = ADComponent(EpicsSignalWithRBV, "NDArrayMode")

def make_detector(name, inherit = None, **kwargs):
    if not inherit:
        inherit = (SoftTrigger, DetectorBase)
    def warmup(obj):
        obj.hdf1.warmup()
        obj.cam.warmup()
        if not sum(obj.hdf1.array_size.get()):
            raise UnprimedPlugin("%s failed to warm up" % obj.hdf1.vname())
    def monitor(obj, dnotify):
        return obj.image1.monitor(dnotify)
    attrs = {
        "_default_read_attrs": ["hdf1"],
        "cam": Component(MyCam, "cam1:"),
        "hdf1": Component(CptHDF5, "HDF1:", write_path_template = "/"),
        "image1": Component(MyImagePlugin, "image1:"),
        "warmup": warmup, "monitor": monitor
    }
    for k, v in kwargs.items():
        if v is None:
            attrs.pop(k, None)
        else:
            attrs[k] = v
    return type(name, inherit, attrs)

def make_dxp(name, cam, nchan = 0):
    ids = [i + 1 for i in range(nchan)]
    attrs = {"_default_read_attrs":
        sum([["ch%d_real" % i, "ch%d_live" % i] for i in ids], ["hdf1"])}
    attrs.update(sum([[
        ("ch%d_real" % i,
            ADComponent(EpicsSignalRO, "dxp%d:ElapsedRealTime" % i)),
        ("ch%d_live" % i,
            ADComponent(EpicsSignalRO, "dxp%d:ElapsedLiveTime" % i)),
    ] for i in ids], []))
    return make_detector(
        name, (DxpTrigger, DxpDetectorBase), cam = Component(cam, ""),
        hdf1 = Component(CptHDF5Dxp, "HDF1:", write_path_template = "/"),
        image1 = None, monitor = None, **attrs
    )

MyAreaDetector = make_detector("MyAreaDetector")
BaseAreaDetector = make_detector\
    ("BaseAreaDetector", image1 = None, monitor = None)
DxpDetector = lambda *args, nchan = 0, **kwargs: \
    make_dxp("DxpDetector", DxpCam, nchan = nchan)(*args, **kwargs)
SitoroDetector = lambda *args, nchan = 0, **kwargs: \
    make_dxp("SitoroDetector", SitoroCam, nchan = nchan)(*args, **kwargs)

