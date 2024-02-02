import h5py
import numpy
import os
import queue
import threading
from PIL import Image
from ophyd import Component, Signal, ADComponent, \
    EpicsSignalWithRBV, AreaDetector, CamBase, SingleTrigger
from ophyd.signal import AttributeSignal
from ophyd.sim import SynSignal
from .ad import CptHDF5
from .ophyd import ThrottleMonitor

class SimImage(ThrottleMonitor):
    image, func = Component(SynSignal), None

    def __init__(self, *, name, func = None, **kwargs):
        super().__init__(name = name, **kwargs)
        if func is not None:
            self.func = lambda: func(self)
        if self.func is not None:
            self.image.sim_set_func(self.func)

    def trigger(self):
        return self.image.trigger()

    def monitor(self, dnotify, typ = "image"):
        _timestamp = [0.0]
        def cb(*, value, timestamp, **kwargs):
            if value is not None and self.maybe_monitor(_timestamp, timestamp):
                dnotify("monitor/" + typ, {
                    "data": {self.image.name: value},
                    "timestamps": {self.image.name: timestamp}
                })
        return self.image.subscribe(cb)

class SimMotorImage(SimImage):
    _lock = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()

    def trigger(self):
        with self._lock:
            return self.image.trigger()

    def mbind(self, motors):
        _timestamp = [0.0]
        def cb(*, value, timestamp, **kwargs):
            if value is None or not self._lock.acquire():
                return
            try:
                if self.maybe_monitor(_timestamp, timestamp):
                    self.image.trigger().wait()
            finally:
                self._lock.release()
        return [m.subscribe(cb) for m in motors]

    def monitor(self, dnotify, typ = "image"):
        def cb(*, value, timestamp, **kwargs):
            if value is not None:
                dnotify("monitor/" + typ, {
                    "data": {self.image.name: value},
                    "timestamps": {self.image.name: timestamp}
                })
        return self.image.subscribe(cb)

class SimCounterImage(SimImage):
    src = dataset = counter = None

    def bind(self, src):
        self.src = src

    def stage(self):
        super().stage()
        self.counter = 0

    def unstage(self):
        self.dataset = self.counter = None
        super().unstage()

    def func(self):
        self.counter = (self.counter + 1) % len(self.dataset)
        return self.dataset[self.counter]

class SimHDF5Image(SimCounterImage):
    def stage(self):
        super().stage()
        self.dataset = h5py.File(self.src)["entry/data/data"]

    def unstage(self):
        self.dataset.file.close()
        super().unstage()

class SimPILImage(SimCounterImage):
    def bind(self, src, open = Image.open):
        self.src, self.open = src, open

    def stage(self):
        super().stage()
        self.dataset = numpy.array\
            ([numpy.array(self.open(f)) for f in self.src])

class CptSimHDF5(CptHDF5):
    src = dest = thread = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.q = queue.Queue()

    def warmup(self):
        with h5py.File(self.parent.src, "r") as f:
            self.src = f["entry/data/data"][:]

    def stage(self):
        super().stage()
        dest = self.full_file_name.get()
        os.remove(dest)
        dest = h5py.File(dest, "a", libver = "latest")
        dest.swmr_mode = True
        with h5py.File(self.parent.template, "r") as f:
            f.copy("entry", dest)

        dest.pop("entry/data/data")
        dest.pop("entry/instrument/detector/data")
        dest.create_dataset("entry/instrument/detector/data",
            (0,) + self.src.shape[1:], dtype = self.src.dtype,
            maxshape = (None,) + self.src.shape[1:],
            chunks = (1,) + self.src.shape[1:])
        dest["entry/data/data"] = dest["entry/instrument/detector/data"]
        self.dest = dest["entry/data/data"]

        self.thread = threading.Thread(target = self.grabber, daemon = False)
        self.thread.start()

    def unstage(self):
        self.q.put("finish")
        self.dest.file.close()
        self.thread.join()
        self.dest = self.thread = None
        super().unstage()

    def grabber(self):
        idle = True
        while True:
            msg = self.q.get()
            if msg == "finish":
                return
            elif idle:
                assert msg == "acquire"
                threading.Thread(target = self.writer, daemon = False).start()
                idle = False
            else:
                assert msg == "idle"
                self.parent.cam.acquire.put(0)
                idle = True

    def writer(self):
        delta = self.parent.cam.num_images.get()
        m, n = self.src.shape[0], self.dest.shape[0]
        i = n % m
        d, j = delta, min(delta, m - i)
        self.dest.resize(n + delta, 0)
        while d:
            self.dest[n : n + j] = self.src[i : i + j]
            n, d = n + j, d - j
            i, j = 0, min(d, m)
        counter = self.parent.cam.array_counter
        counter.put(counter.get() + delta)
        self.q.put("idle")

class SimHDF5Acquire(Signal):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hdf1 = self.parent.parent.hdf1

    def put(self, value, **kwargs):
        assert not kwargs.get("wait")
        old_value = self._readback
        self._readback = value
        self._run_subs(sub_type = self.SUB_VALUE,
            old_value = old_value, value = value)
        if value and not old_value:
            self.hdf1.q.put("acquire")

class SimHDF5Cam(CamBase):
    acquire = ADComponent(SimHDF5Acquire, value = 0)
    _acquire = ADComponent(EpicsSignalWithRBV, "Acquire")

class SimHDF5Detector(SingleTrigger, AreaDetector):
    _default_read_attrs = ["hdf1"]
    cam = Component(SimHDF5Cam, "cam1:")
    hdf1 = Component(CptSimHDF5, "HDF1:", write_path_template = "/")

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix = prefix, **kwargs)

    def bind(self, src, template):
        self.src, self.template = src, template

    def warmup(self):
        self.hdf1.enable.set(1).wait()
        self.cam.array_callbacks.set(1).wait()
        self.cam._acquire.set(1).wait()
        self.hdf1.warmup()

    def make_data_key(self):
        return dict(shape = (0,) + self.hdf1.src.shape[1:],
            source = "PV:{}".format(self.prefix),
            dtype = "array", external = "FILESTORE:")

