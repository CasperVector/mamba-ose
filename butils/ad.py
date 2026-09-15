import re
import time
import numpy
import threading
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO, \
    ADBase, ADComponent, EpicsSignalWithRBV, DetectorBase, ADTriggerStatus
from ophyd.device import BlueskyInterface, DynamicDeviceComponent, \
    GenerateDatumInterface, Staged, STAGE_KEEP
from ophyd.signal import AttributeSignal
from ophyd.status import Status
from ophyd.areadetector.base import ad_group
from ophyd.areadetector.filestore_mixins import \
    FileStoreHDF5, FileStoreIterativeWrite
from ophyd.areadetector.paths import EpicsPathSignal
from ophyd.utils.errors import UnprimedPlugin
from .ophyd import ThrottleMonitor

class AcquireTimeout(Device):
    timeout = Component(AttributeSignal, attr = "_timeout", kind = "config")
    _timeout, _timer, _status = 0.0, None, None

    def __init__(self, *args, acquire = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._acquire = acquire

    def stage(self):
        self._acquire.subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        super().unstage()
        self._acquire.clear_sub(self._acquire_changed)
        self._finish_status(False)

    def trigger(self):
        self._status = status = Status(self)
        return status

    def _finish_status(self, success):
        timer, self._timer = self._timer, None
        status, self._status = self._status, None
        if timer:
            timer.cancel()
        if status:
            status._finished(success)

    def _acquire_changed(self, *, value, old_value, **kwargs):
        if old_value == 1 and value == 0:
            self._finish_status(True)
        elif old_value == 0 and value == 1 and not self._timer:
            self._timer = timer = threading.Timer(self._timeout,
                lambda: self._finish_status(False))
            timer.daemon = True
            timer.start()

class MyTriggerBase(BlueskyInterface):
    _status_type = ADTriggerStatus

    def __init__(self, *args, image_name = None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = "_".join([self.name, "image"])
        self._image_name, self._datum_keys = image_name, [image_name]

class SoftTrigger(MyTriggerBase):
    _acquisition_signal = "cam.acquire"
    _counter_signal = _trigger_delay = _orig_acquire = _status = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._acquisition_signal:
            self._acquisition_signal = getattr(self, self._acquisition_signal)
        if self._counter_signal:
            self._counter_signal = getattr(self, self._counter_signal)
        acquire = "cam.acquire" if hasattr(self, "cam") else "acquire"
        self._acquire = getattr(self, acquire)
        stage_acquire = int(self._acquisition_signal != self._acquire)
        self.stage_sigs.update([(acquire, stage_acquire)])

    def stage(self):
        self._orig_acquire = self._acquire.get()
        stage_acquire = int(self._acquisition_signal != self._acquire)
        if self._orig_acquire == stage_acquire == 1:
            self._acquire.set(0, timeout = 10.0).wait()
        if not self._counter_signal:
            self._acquisition_signal.subscribe(self._acquire_changed)
        elif self._trigger_delay is None:
            self._counter_signal.subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        super().unstage()
        if not self._counter_signal:
            self._acquisition_signal.clear_sub(self._acquire_changed)
        elif self._trigger_delay is None:
            self._counter_signal.clear_sub(self._acquire_changed)
        stage_acquire = int(self._acquisition_signal != self._acquire)
        if self._orig_acquire == stage_acquire == 1:
            self._acquire.set(1, timeout = 10.0).wait()

    def trigger(self):
        assert self._staged == Staged.yes
        delayed = self._trigger_delay is not None and self._counter_signal
        status = self._status_type(self)
        if not delayed:
            self._status = status
        self._acquisition_signal.put(1)
        if hasattr(self, "cam"):
            self.dispatch(self._image_name, time.time())
            acquire_time = self.cam.acquire_time
        else:
            acquire_time = self.acquire_time
        if delayed:
            timer = threading.Timer\
                (acquire_time.get() + self._trigger_delay, status.set_finished)
            timer.daemon = True
            timer.start()
        return status

    def _acquire_changed(self, *, value, old_value, **kwargs):
        status = self._status
        if status is None:
            return
        if (self._counter_signal and value) or (old_value == 1 and value == 0):
            self._status = None
            status.set_finished()

class QSoftTrigger(SoftTrigger):
    _status_type = Status
    _acquisition_signal = "acquire"

class MyDetectorBase(DetectorBase):
    def __init__(self, *args, hdf5_dir = None, **kwargs):
        super().__init__(*args, **kwargs)
        if hdf5_dir is not None:
            self.set_hdf5_dir(hdf5_dir)

    def set_hdf5_dir(self, path):
        if not path.startswith("/"):
            assert re.match("[A-Za-z]:[/\\\\]", path)
            self.hdf1.path_semantics = "windows"
            self.hdf1.read_path_template = "/dev/null"
        self.hdf1.write_path_template = path

class MyPluginBase(ADBase):
    enable, array_counter, blocking_callbacks = [
        Component(EpicsSignalWithRBV, suffix, kind = "config")
        for suffix in ["EnableCallbacks", "ArrayCounter", "BlockingCallbacks"]
    ]
    array_size = DynamicDeviceComponent(ad_group(EpicsSignalRO, (
        ("depth", "ArraySize2_RBV"), ("height", "ArraySize1_RBV"),
        ("width", "ArraySize0_RBV"),
    )))

class MyFileBase(Device):
    capture, file_number = [
        Component(EpicsSignalWithRBV, suffix)
        for suffix in ["Capture", "FileNumber"]
    ]
    num_capture, auto_increment, auto_save, file_write_mode = [
        Component(EpicsSignalWithRBV, suffix, kind = "config") for suffix in
        ["NumCapture", "AutoIncrement", "AutoSave", "FileWriteMode"]
    ]
    file_template, file_name = [
        Component(EpicsSignalWithRBV, suffix, string = True, kind = "config")
        for suffix in ["FileTemplate", "FileName"]
    ]
    file_path_exists = Component(EpicsSignalRO,
        "FilePathExists_RBV", kind = "config")
    full_file_name = Component(EpicsSignalRO,
        "FullFileName_RBV", string = True, kind = "config")
    file_path = Component(EpicsPathSignal, "FilePath",
        string = True, path_semantics = "posix", kind = "config")

class MyHDF5Plugin(MyPluginBase, MyFileBase, GenerateDatumInterface):
    swmr_mode = ADComponent(EpicsSignalWithRBV, "SWMRMode")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update({"blocking_callbacks": 1, "enable": 1})

class CptHDF5(MyHDF5Plugin, FileStoreHDF5, FileStoreIterativeWrite):
    def get_frames_per_point(self):
        parent = self.parent
        return 1 if parent._counter_signal else parent.cam.num_images.get()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filestore_spec = "AD_HDF5_SWMR"

    def warmup(self):
        self.configure({"swmr_mode": 1}, action = True)

class MyImagePlugin(ThrottleMonitor, MyPluginBase):
    array_data = ADComponent(EpicsSignalRO, "ArrayData")
    array_size = DynamicDeviceComponent(ad_group(EpicsSignalRO, (
        ("depth", "ArraySize2_RBV"), ("height", "ArraySize1_RBV"),
        ("width", "ArraySize0_RBV"),
    ), auto_monitor = True))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update({"blocking_callbacks": 0, "enable": 0})

    def monitor(self, dnotify):
        if not hasattr(self, "_monitor_cb"):
            image_name, _timestamp = self.parent._image_name, [0.0]
            def cb(*, value, timestamp, **kwargs):
                if value is None or \
                    not self.maybe_monitor(_timestamp, timestamp):
                    return
                shape = list(self.array_size.get())
                while True:
                    if not shape:
                        return
                    if all(shape):
                        break
                    shape.pop(0)
                dnotify("monitor/image", {
                    "data": {image_name:
                         value[:numpy.prod(shape)].reshape(shape)},
                    "timestamps": {image_name: timestamp},
                })
            self._monitor_cb = cb
        self.array_data.clear_sub(self._monitor_cb)
        return self.array_data.subscribe(self._monitor_cb, run = False)

class MyCamBase(ADBase):
    array_callbacks, array_counter = [
        Component(EpicsSignalWithRBV, suffix)
        for suffix in ["ArrayCallbacks", "ArrayCounter"]
    ]
    array_size = DynamicDeviceComponent(ad_group(EpicsSignalRO, (
        ("array_size_z", "ArraySizeZ_RBV"), ("array_size_y", "ArraySizeY_RBV"),
        ("array_size_x", "ArraySizeX_RBV"),
    )))

class MyCam(MyCamBase):
    acquire, trigger_mode, image_mode, num_images, \
        acquire_time, acquire_period, bin_x, bin_y, min_x, min_y = [
        Component(EpicsSignalWithRBV, suffix) for suffix in [
            "Acquire", "TriggerMode", "ImageMode", "NumImages",
            "AcquireTime", "AcquirePeriod", "BinX", "BinY", "MinX", "MinY",
        ]
    ]
    num_images_counter, max_size_x, max_size_y = [
        Component(EpicsSignalRO, suffix) for suffix in
        ["NumImagesCounter_RBV", "MaxSizeX_RBV", "MaxSizeY_RBV"]
    ]
    size = DynamicDeviceComponent(ad_group(EpicsSignalWithRBV,
        (("size_x", "SizeX"), ("size_y", "SizeY"))))
    _default_configuration_attrs = MyCamBase._default_configuration_attrs + (
        "trigger_mode", "image_mode", "num_images", "acquire_time",
        "acquire_period", "bin_x", "bin_y", "min_x", "min_y",
        "max_size_x", "max_size_y", "size.size_x", "size.size_y",
    )
    _warmup_sleep = 1.0, 1.0

    def warmup(self):
        sigs = [(self.acquire, 1)]
        orig_vals = [(sig, sig.get()) for sig, val in sigs]
        self.array_callbacks.put(1)
        for sig, val in sigs:
            sig.put(val)
            time.sleep(0.1)
        for i in range(int(self._warmup_sleep[0] / 0.1)):
            if self.acquire.get():
                break
            time.sleep(0.1)
        for i in range(int(self._warmup_sleep[1] / 0.1)):
            if not self.acquire.get():
                break
            time.sleep(0.1)
        for sig, val in reversed(orig_vals):
            sig.set(val, timeout = 10.0).wait()

def make_detector(name, inherit = (SoftTrigger, MyDetectorBase), **kwargs):
    def warmup(obj):
        obj.hdf1.enable.set(1, timeout = 10.0).wait()
        obj.hdf1.warmup()
        obj.cam.warmup()
        obj.hdf1.enable.set(0, timeout = 10.0).wait()
        if not sum(obj.hdf1.array_size.get()):
            raise UnprimedPlugin("%s failed to warm up" % obj.hdf1.vname())
    def monitor(obj, dnotify):
        return obj.image1.monitor(dnotify)
    attrs = {
        "_default_read_attrs": ["hdf1"],
        "cam": Component(MyCam, "cam1:"),
        "hdf1": Component(CptHDF5, "HDF1:", write_path_template = "/"),
        "image1": Component(MyImagePlugin, "image1:"),
        "warmup": warmup, "monitor": monitor,
    }
    for k, v in kwargs.items():
        if v is None:
            attrs.pop(k, None)
        else:
            attrs[k] = v
    return type(name, inherit, attrs)

class QDetectorBase(Device):
    def cfg_trans(self, dev, cfg):
        return {re.sub(r"^cam\.", "", k): v for k, v in cfg.items()}

def make_qdetector(name, nout = 1, inherit = (QSoftTrigger, QDetectorBase)):
    attrs = {
        "acquire": Component(EpicsSignal, "acquire", kind = "omitted"),
        "num_images": Component(EpicsSignal, "num_images", kind = "config"),
        "num_images_counter":
            Component(EpicsSignal, "num_images_counter", kind = "omitted"),
        "warmup": (lambda obj: None),
    }
    attrs.update({"output%d" % i: Component(
        EpicsSignal, "output%d" % i, string = True, kind = "config"
    ) for i in range(nout)})
    return type(name, inherit, attrs)

MyAreaDetector = make_detector("MyAreaDetector")
BaseAreaDetector = make_detector\
    ("BaseAreaDetector", image1 = None, monitor = None)
QDetector = make_qdetector("QDetector")
QDetector0 = make_qdetector("QDetector", 0)
QDetector2 = make_qdetector("QDetector", 2)

class DxpTrigger(MyTriggerBase):
    def warmup(self):
        self.cam.stop_all.put(1, use_complete = True)
        time.sleep(0.5)
        self.stage_sigs.update({"collect_mode": STAGE_KEEP,
            "ignore_gate": STAGE_KEEP, "pixels_per_run": STAGE_KEEP})
        cfg = {"collect_mode": 0, "ignore_gate": 1,
            "pixels_per_run": 1, "preset_mode": 1, "preset_real": 0.1}
        if hasattr(self.cam, "ndarray_mode"):
            self.stage_sigs.update({"pixel_advance_mode": STAGE_KEEP})
            cfg.update({"pixel_advance_mode": 0, "ndarray_mode": 1})
        self.cam.configure(cfg)

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

class DxpDetectorBase(MyDetectorBase):
    make_data_key = lambda self: dict(
        shape = (1,) + tuple(self.hdf1.array_size.get())[-2:],
        source = "PV." + self.prefix, dtype = "array", external = "FILESTORE:"
    )

class CptHDF5Dxp(CptHDF5):
    get_frames_per_point = lambda self: 1

class DxpCam(MyCamBase):
    collect_mode, ignore_gate, input_logic_polarity, \
        pixel_advance_mode, pixels_per_run, \
        pixels_per_buffer, auto_pixels_per_buffer = [
        Component(EpicsSignalWithRBV, suffix) for suffix in [
            "CollectMode", "IgnoreGate", "InputLogicPolarity",
            "PixelAdvanceMode", "PixelsPerRun",
            "PixelsPerBuffer", "AutoPixelsPerBuffer",
        ]
    ]
    preset_mode, preset_real, erase_start, stop_all, next_pixel = [
        Component(EpicsSignal, suffix) for suffix in
        ["PresetMode", "PresetReal", "EraseStart", "StopAll", "NextPixel"]
    ]
    acquiring = ADComponent(EpicsSignalRO, "Acquiring")
    _default_configuration_attrs = MyCamBase._default_configuration_attrs + (
        "collect_mode", "ignore_gate", "input_logic_polarity",
        "pixel_advance_mode", "pixels_per_run", "pixels_per_buffer",
        "auto_pixels_per_buffer", "preset_mode", "preset_real",
    )

    def warmup(self):
        self.array_callbacks.put(1)
        self.erase_start.put(1)
        time.sleep(min(2.0, self.preset_real.get()))
        self.stop_all.put(1)

class SitoroCam(DxpCam):
    ndarray_mode = ADComponent(EpicsSignalWithRBV, "NDArrayMode")
    _default_configuration_attrs = \
        DxpCam._default_configuration_attrs + ("ndarray_mode",)

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
    def warmup(obj):
        DxpTrigger.warmup(obj)
        BaseAreaDetector.warmup(obj)
    return make_detector(
        name, (DxpTrigger, DxpDetectorBase), cam = Component(cam, ""),
        hdf1 = Component(CptHDF5Dxp, "HDF1:", write_path_template = "/"),
        image1 = None, monitor = None, warmup = warmup, **attrs
    )

NDDxp = lambda *args, nchan = 0, **kwargs: \
    make_dxp("NDDxp", DxpCam, nchan = nchan)(*args, **kwargs)
NDSitoro = lambda *args, nchan = 0, **kwargs: \
    make_dxp("NDSitoro", SitoroCam, nchan = nchan)(*args, **kwargs)

class Xspress3Trigger(SoftTrigger):
    def use_trig(self, val):
        if val:
            self._acquisition_signal = self.cam.soft_trigger
            self._counter_signal = self.hdf1.array_counter
            self.stage_sigs.update({"cam.trigger_mode": 7,
                "cam.num_images": 12216, "cam.acquire": 1})
        else:
            self._acquisition_signal = self.cam.acquire
            self._counter_signal = None
            self.stage_sigs.update({"cam.trigger_mode": 1,
                "cam.num_images": 1, "cam.acquire": 0})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_trig(False)
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure\
            ({"trigger_mode": 1, "num_images": 1, "acquire_time": 0.1})

    def config_fly(self, atime = None, period = None):
        return {"cam.trigger_mode": 3}

    def _maybe_erase(self):
        if not self.cam.erase_on_start.get():
            self.cam.erase.put(1, use_complete = True)

    def stage(self):
        self._orig_acquire = self._acquire.get()
        if self._counter_signal:
            assert self.cam.num_images.get() > 0
            if self._orig_acquire:
                self._acquire.set(0, timeout = 10.0).wait()
            self._acquisition_signal.put(0)
            self._maybe_erase()
        (self._counter_signal or self._acquisition_signal)\
            .subscribe(self._acquire_changed)
        MyTriggerBase.stage(self)

    def trigger(self):
        if not self._counter_signal:
            self._maybe_erase()
        elif self.cam.array_counter.get() >= self.cam.num_images.get():
            self._acquire.set(0, timeout = 10.0).wait()
            self._maybe_erase()
            self._acquire.set(1, timeout = 10.0).wait()
        return super().trigger()

    def _acquire_changed(self, *, value, old_value, **kwargs):
        status = self._status
        if status is None:
            return
        if (self._counter_signal and value) or (old_value == 1 and value == 0):
            self._status = None
            if self._counter_signal:
                self._acquisition_signal.put(0)
            status.set_finished()

class Xspress3Cam(MyCam):
    erase = ADComponent(EpicsSignal, "ERASE")
    soft_trigger = ADComponent(EpicsSignal, "SoftTrigger")
    erase_on_start = ADComponent(EpicsSignal, "EraseOnStart")
    _warmup_sleep = 2.0, 1.0

def make_xspress3(name, nchan = 0):
    ids = [i + 1 for i in range(nchan)]
    attrs = {"_default_read_attrs": ["ch%d_dtperc" % i for i in ids] + ["hdf1"]}
    attrs.update([("ch%d_dtperc" % i,
        ADComponent(EpicsSignalRO, "ch%d:DeadTime_RBV" % i)) for i in ids])
    def warmup(obj):
        Xspress3Trigger.warmup(obj)
        BaseAreaDetector.warmup(obj)
    return make_detector(
        name, (Xspress3Trigger, MyDetectorBase),
        cam = Component(Xspress3Cam, "cam1:"),
        image1 = None, monitor = None, warmup = warmup, **attrs
    )

ADXspress3 = lambda *args, nchan = 0, **kwargs: \
    make_xspress3("ADXspress3", nchan = nchan)(*args, **kwargs)

class CoreTrigger(SoftTrigger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update({"cam.trigger_mode": STAGE_KEEP,
            "cam.image_mode": STAGE_KEEP, "cam.num_images": STAGE_KEEP})
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"trigger_mode": 0, "image_mode": 1,
            "num_images": 1, "acquire_time": 0.1})
        super().warmup()

class MythenCam(MyCam):
    threshold_energy = ADComponent(EpicsSignalWithRBV,
        "ThresholdEnergy", rtolerance = 1e-6)
    _default_configuration_attrs = MyCam._default_configuration_attrs + \
        ("threshold_energy",)

class ADMythen(CoreTrigger, BaseAreaDetector):
    cam = Component(MythenCam, "cam1:")

class ADPandABlocks(BaseAreaDetector):
    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"image_mode": 1, "num_images": 1})
        super().warmup()
        self.cam.configure({"image_mode": 2})

class QDPanda(QDetector2):
    def warmup(self):
        self.acquire.set(0, timeout = 10.0).wait()
        self.configure({"num_images": 0})

class CoreMonitor(SoftTrigger):
    def prep_monitor(self, lnotify = None):
        self.stage_sigs.update\
            ({"cam.image_mode": 1, "cam.acquire_period": 0.101})
        self.stage_sigs.move_to_end("cam.acquire")
        self.configure({
            "image1.monitor_period": 0.100, "image1.enable": 1,
            "cam.image_mode": 2, "cam.acquire_period": 0.101,
        }, action = True)
        if lnotify:
            self.monitor(lnotify)

class AtimeMonitor(SoftTrigger):
    def prep_monitor(self, lnotify = None):
        self.stage_sigs.update\
            ({"cam.image_mode": 1, "cam.acquire_time": 0.101})
        self.stage_sigs.move_to_end("cam.acquire")
        self.configure({
            "image1.monitor_period": 0.100, "image1.enable": 1,
            "cam.image_mode": 2, "cam.acquire_time": 0.101,
        }, action = True)
        if lnotify:
            self.monitor(lnotify)

class ADCore(CoreMonitor, CoreTrigger, MyAreaDetector): pass
class ADAtime(AtimeMonitor, CoreTrigger, MyAreaDetector): pass

class ADAndor3(CoreTrigger, MyAreaDetector):
    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"trigger_mode": "Internal",
            "image_mode": "Fixed", "num_images": 1, "acquire_time": 0.1})
        MyAreaDetector.warmup(self)

    def prep_monitor(self, lnotify = None):
        self.stage_sigs.update\
            ({"cam.image_mode": "Fixed", "cam.acquire_period": 0.101})
        self.stage_sigs.move_to_end("cam.acquire")
        self.configure({
            "image1.monitor_period": 0.100, "image1.enable": 1,
            "cam.image_mode": "Continuous", "cam.acquire_period": 0.101,
        }, action = True)
        if lnotify:
            self.monitor(lnotify)

    def config_fly(self, atime = None, period = None):
        return {"cam.trigger_mode": "External Exposure"}

class HamamatsuCam(MyCam):
    trigger_source = ADComponent(EpicsSignalWithRBV, "TriggerSource")
    trigger_active = ADComponent(EpicsSignalWithRBV, "TriggerActive")
    software_trigger = ADComponent(EpicsSignal, "DCAMSoftwareTrigger")
    _default_configuration_attrs = MyCam._default_configuration_attrs + \
        ("trigger_source", "trigger_active")
    _warmup_sleep = 2.0, 1.0

class ADHamamatsu(AtimeMonitor, MyAreaDetector):
    cam = Component(HamamatsuCam, "cam1:")

    def use_trig(self, val):
        if val:
            self._acquisition_signal = self.cam.software_trigger
            self._counter_signal = self.hdf1.array_counter
            self.stage_sigs.update({"cam.trigger_source": 2,
                "cam.image_mode": 2, "cam.acquire": 1})
        else:
            self._acquisition_signal = self.cam.acquire
            self._counter_signal = None
            self.stage_sigs.update({"cam.trigger_source": 0,
                "cam.image_mode": 1, "cam.acquire": 0})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_trig(False)
        self.stage_sigs.update({"cam.num_images": STAGE_KEEP})
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({
            "trigger_mode": 0, "trigger_source": 0, "trigger_active": 1,
            "image_mode": 1, "num_images": 1, "acquire_time": 0.1,
        })
        super().warmup()

    def config_fly(self, atime = None, period = None):
        return {"cam.trigger_source": 1}

class ADIRay(CoreMonitor, MyAreaDetector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cam._warmup_sleep = 5.0, 5.0
        self.stage_sigs.update({
            "cam.trigger_mode": STAGE_KEEP, "cam.image_mode": STAGE_KEEP,
            "cam.num_images": STAGE_KEEP, "cam.acquire_period": STAGE_KEEP,
        })
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"trigger_mode": 2, "image_mode": 1,
            "num_images": 1, "acquire_period": 0.1})
        super().warmup()

    def config_fly(self, atime, period):
        return {"cam.trigger_mode": 1, "cam.acquire_period": atime}

class LambdaCam(MyCam):
    gating_mode, dual_mode, operating_mode = [
        ADComponent(EpicsSignalWithRBV, suffix)
        for suffix in ["GatingMode", "DualMode", "OperatingMode"]
    ]
    energy_threshold, dual_threshold = [
        ADComponent(EpicsSignalWithRBV, suffix, rtolerance = 1e-6)
        for suffix in ["EnergyThreshold", "DualThreshold"]
    ]
    _default_configuration_attrs = MyCam._default_configuration_attrs + (
        "gating_mode", "dual_mode", "operating_mode",
        "energy_threshold", "dual_threshold",
    )

class ADLambda(MyAreaDetector):
    cam = Component(LambdaCam, "cam1:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update\
            ({"cam.gating_mode": STAGE_KEEP, "cam.num_images": STAGE_KEEP})
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"trigger_mode": 0, "gating_mode": 0,
            "num_images": 1, "acquire_time": 0.1})
        super().warmup()

    def config_fly(self, atime = None, period = None):
        return {"cam.gating_mode": 1}

class MinipixCam(MyCam):
    operation_mode = ADComponent(EpicsSignalWithRBV, "OperationMode")
    threshold_energy = ADComponent(EpicsSignalWithRBV,
        "ThresholdEnergy", rtolerance = 1e-6)
    _default_configuration_attrs = MyCam._default_configuration_attrs + \
        ("operation_mode", "threshold_energy", "bias")

class ADMinipix(CoreTrigger, MyAreaDetector):
    cam = Component(MinipixCam, "cam1:")

class ADPICam(MyAreaDetector):
    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({"trigger_mode": 0, "image_mode": 1,
            "num_images": 1, "acquire_time": 0.1e3})
        super().warmup()

class TucsenCam(MyCam):
    trig_soft = ADComponent(EpicsSignalWithRBV, "TUTrigSoftSignal")
    trig_exp_type = ADComponent(EpicsSignalWithRBV, "TrigExpType")
    bin_mode = ADComponent(EpicsSignalWithRBV, "BinMode")
    frame_rate = ADComponent(EpicsSignalWithRBV,
        "AcquisitionFrameRate", tolerance = 1.0)
    _default_configuration_attrs = MyCam._default_configuration_attrs + \
        ("trig_exp_type", "bin_mode", "frame_rate")

class ADTucsen(AtimeMonitor, MyAreaDetector):
    cam = Component(TucsenCam, "cam1:")

    def use_trig(self, val):
        if val:
            self._acquisition_signal = self.cam.trig_soft
            self._counter_signal = self.hdf1.array_counter
            self.stage_sigs.update\
                ({"cam.trigger_mode": 2, "cam.image_mode": 2, "cam.acquire": 1})
        else:
            self._acquisition_signal = self.cam.acquire
            self._counter_signal = None
            self.stage_sigs.update\
                ({"cam.trigger_mode": 0, "cam.image_mode": 1, "cam.acquire": 0})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_trig(False)
        self.stage_sigs.update({"cam.num_images": STAGE_KEEP})
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.trigger_mode.set(1, timeout = 10.0).wait()
        self.cam.trig_exp_type.set(1, timeout = 10.0).wait()
        self.cam.trigger_mode.set(0, timeout = 10.0).wait()
        self.cam.configure({"image_mode": 1,
            "num_images": 1, "acquire_time": 0.1})
        super().warmup()

    def config_fly(self, atime = None, period = None):
        return {"cam.trigger_mode": 1}

class XimeaCam(MyCam):
    acquire_time = ADComponent(EpicsSignalWithRBV,
        "AcquireTime", rtolerance = 1e-3)
    acquire_period = ADComponent(EpicsSignalWithRBV,
        "AcquirePeriod", rtolerance = 1e-3)
    acq_timing_mode = ADComponent(EpicsSignalWithRBV, "GC_AcqTimingMode")
    trg_source = ADComponent(EpicsSignalWithRBV, "GC_TrgSource")
    trg_selector = ADComponent(EpicsSignalWithRBV, "GC_TrgSelector")
    _default_configuration_attrs = MyCam._default_configuration_attrs + \
        ("acq_timing_mode", "trg_source", "trg_selector")

class ADXimea(MyAreaDetector):
    cam = Component(XimeaCam, "cam1:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update({
            "cam.acq_timing_mode": STAGE_KEEP, "cam.trg_source": STAGE_KEEP,
            "cam.image_mode": STAGE_KEEP, "cam.num_images": STAGE_KEEP,
            "cam.acquire_time": STAGE_KEEP, "cam.acquire_period": STAGE_KEEP,
        })
        self.stage_sigs.move_to_end("cam.acquire")

    def warmup(self):
        self.cam.acquire.set(0, timeout = 10.0).wait()
        self.cam.configure({
            "acq_timing_mode": 1, "trg_source": 0,
            "trg_selector": 0, "image_mode": 1, "num_images": 1,
            "acquire_time": 0.1, "acquire_period": 0.2,
        })
        super().warmup()

    def prep_monitor(self, lnotify = None):
        self.stage_sigs.update({"cam.image_mode": 1,
            "cam.acquire_time": 0.1, "cam.acquire_period": 0.201})
        self.configure({
            "image1.monitor_period": 0.200, "image1.enable": 1,
            "cam.image_mode": 2, "cam.acquire_period": 0.201,
        }, action = True)
        if lnotify:
            self.monitor(lnotify)

    def config_fly(self, atime = None, period = None):
        return {"cam.acq_timing_mode": 0,
            "cam.trg_source": 1, "cam.acquire_time": atime}

    def unstage(self):
        for sig in ["trg_source", "acq_timing_mode", "acquire"]:
            if sig in self._original_vals:
                self._original_vals.move_to_end(getattr(self.cam, sig))
        super().unstage()

class QDEiger1(QDetector2):
    edet_trigger, = [
        Component(EpicsSignal, suffix, kind = "omitted")
        for suffix in ["edet_trigger"]
    ]
    manual_trigger, edet_ntrigger = [
        Component(EpicsSignal, suffix, kind = "config")
        for suffix in ["manual_trigger", "edet_ntrigger"]
    ]
    zaddr, trigger_mode = [
        Component(EpicsSignal, suffix, kind = "config", string = True)
        for suffix in ["zaddr", "trigger_mode"]
    ]
    acquire_time, acquire_period, photon_energy, threshold_energy = [
        Component(EpicsSignal, suffix, kind = "config", rtolerance = 1e-6)
        for suffix in
        ["acquire_time", "acquire_period", "photon_energy", "threshold_energy"]
    ]

    def cfg_trans(self, dev, cfg):
        cfg, _cfg = {}, cfg
        for k, v in _cfg.items():
            if k in ["cam.num_images", "cam.num_triggers"]:
                k = "edet_ntrigger"
            cfg[k] = v
        return super().cfg_trans(dev, cfg)

    def use_trig(self, val):
        if val:
            self._acquisition_signal = self.edet_trigger
            self._counter_signal = self.num_images_counter
            self.stage_sigs.update\
                ({"manual_trigger": 1, "edet_ntrigger": 10000000, "acquire": 1})
        else:
            self._acquisition_signal = self.acquire
            self._counter_signal = None
            self.stage_sigs.update\
                ({"manual_trigger": 0, "edet_ntrigger": 1, "acquire": 0})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_trig(False)
        self.stage_sigs.update({
            "trigger_mode": STAGE_KEEP, "edet_ntrigger": STAGE_KEEP,
            "acquire_time": STAGE_KEEP, "acquire_period": STAGE_KEEP,
        })
        self.stage_sigs.move_to_end("acquire")

    def warmup(self):
        self.acquire.set(0, timeout = 10.0).wait()
        self.configure({
            "manual_trigger": 0, "num_images": 1, "edet_ntrigger": 1,
            "trigger_mode": "ints", "acquire_time": 0.1, "acquire_period": 0.1,
        })

    def config_fly(self, atime, period):
        return {"trigger_mode": "exte",
            "acquire_time": atime, "acquire_period": period}

class QDEiger2(QDEiger1):
    threshold_1_mode, threshold_2_mode, threshold_diff_mode = [
        Component(EpicsSignal, suffix, kind = "config", string = True)
        for suffix in
        ["threshold_1_mode", "threshold_2_mode", "threshold_diff_mode"]
    ]
    threshold_2_energy, = [
        Component(EpicsSignal, suffix, kind = "config", rtolerance = 1e-6)
        for suffix in ["threshold_2_energy"]
    ]

    def warmup(self):
        super().warmup()
        self.configure({
            "threshold_1_mode": "enabled", "threshold_2_mode": "enabled",
            "threshold_diff_mode": "enabled",
        })

class QDPeak(QDetector):
    acquire_time, dwell_time, pass_energy, \
        x_step, x_min, x_max, x_center, x_width, x_delta, \
        y_step, y_min, y_max, y_center, y_width, y_delta, \
        z_step, z_min, z_max, z_center, z_width, z_delta = [
        Component(EpicsSignal, suffix, rtolerance = 1e-6,
            kind = "config", put_complete = True) for suffix in [
            "acquire_time", "dwell_time", "pass_energy",
            "x_step", "x_min", "x_max", "x_center", "x_width", "x_delta",
            "y_step", "y_min", "y_max", "y_center", "y_width", "y_delta",
            "z_step", "z_min", "z_max", "z_center", "z_width", "z_delta",
        ]
    ]
    trigger_enable, x_num, y_num, z_num = [
        Component(EpicsSignal, suffix, kind = "config", put_complete = True)
        for suffix in ["trigger_enable", "x_num", "y_num", "z_num"]
    ]
    lens_mode, x_mode, y_mode, z_mode = [
        Component(EpicsSignal, suffix, string = True,
            kind = "config", put_complete = True) for suffix in
        ["lens_mode", "x_mode", "y_mode", "z_mode"]
    ]
    reset, software_trigger = [
        Component(EpicsSignal, suffix, kind = "omitted", put_complete = True)
        for suffix in ["reset", "software_trigger"]
    ]

    def use_trig(self, val = None):
        if val is not None:
            self._use_trig = val
        val = self._use_trig and all(a.get().title() == "Fixed"
            for a in [self.x_mode, self.y_mode, self.z_mode])
        if val:
            self._acquisition_signal = self.software_trigger
            self._counter_signal = self.num_images_counter
            self.stage_sigs.update\
                ({"trigger_enable": 1, "num_images": 0, "acquire": 1})
        else:
            self._acquisition_signal = self.acquire
            self._counter_signal = None
            self.stage_sigs.update\
                ({"trigger_enable": 0, "num_images": 1, "acquire": 0})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_trig(False)
        self.stage_sigs.move_to_end("acquire")

    def warmup(self):
        self.acquire.set(0, timeout = 10.0).wait()
        self.configure({"trigger_enable": 0, "num_images": 1})

class QDUhss(QDetector):
    _auto_delete, _config_timeouts = 40, {"acquire": 30.0}
    acquire = Component(AttributeSignal,
        attr = "_acquire_attr", kind = "omitted")
    _acquire_raw = Component(EpicsSignal, "acquire", kind = "omitted")
    _acquire_rbv = Component(EpicsSignalRO, "acquire", kind = "omitted")
    detector_state = Component(EpicsSignalRO, "detector_state", string = True)
    num_datasets = Component(EpicsSignalRO, "NumDatasets")
    delete_datasets = Component(EpicsSignal,
        "DeleteDatasets", put_complete = True, kind = "omitted")
    acquisition_mode, output_mode, imaging_mode, \
        calib_label, side_channel, file_path = [
        Component(EpicsSignal, suffix, string = True, kind = "config")
        for suffix in [
            "AcquisitionMode", "OutputMode", "ImagingMode",
            "CalibLabel", "SideChannel", "FilePath",
        ]
    ]
    acquire_time, exposure_interval, lower_energy, upper_energy = [
        Component(EpicsSignal, suffix, kind = "config") for suffix in
        ["acquire_time", "ExposureInterval", "LowerEnergy", "UpperEnergy"]
    ]

    @property
    def _acquire_attr(self):
        return self._acquire_raw.get()

    @_acquire_attr.setter
    def _acquire_attr(self, x):
        if x and not self._acquire_raw.get():
            if self.num_datasets.get() >= self._auto_delete > 0:
                self.delete_datasets.set(1, timeout = 10.0).wait()
            if self.side_channel.get() != "DISABLE":
                try:
                    uid, idx = self.file_path.get().split("_")
                    self.file_path.set("%s_%06d" % (uid, int(idx) + 1),
                        timeout = 10.0).wait()
                except ValueError:
                    pass
        self._acquire_raw.put(x)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update({
            "acquisition_mode": STAGE_KEEP, "side_channel": STAGE_KEEP,
            "num_images": STAGE_KEEP, "acquire_time": STAGE_KEEP,
            "exposure_interval": STAGE_KEEP,
        })
        self.stage_sigs.move_to_end("acquire")

    def warmup(self):
        self.acquire.set(0, timeout = 10.0).wait()
        self.configure({
            "imaging_mode": "B8_1S", "output_mode": "UNSIGNED_8BIT",
            "acquisition_mode": "FIXED_TIME", "side_channel": "DISABLE",
            "num_images": 1, "acquire_time": 0.1, "exposure_interval": 0.1,
        })

    def stage(self):
        self.file_path.set(
            "" if self.side_channel.get() == "DISABLE" else "%s_%06d" %
                ("-".join(str(uuid.uuid4()).split("-")[:-1]), -1),
            timeout = 10.0
        ).wait()
        super().stage()

