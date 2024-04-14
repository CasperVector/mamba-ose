import h5py
import numpy
import pyqtgraph
import bluesky.callbacks.mpl_plotting as mpl_cb
from databroker.v0 import Broker
from bluesky.callbacks.core import CallbackBase

def roi_sum(roi, img):
    img = numpy.array(img)
    return img[roi[2] : roi[3], roi[0] : roi[1]].sum()

def my_broker(d):
    return Broker.from_config({
        "description": "test",
        "metadatastore": {
            "module": "databroker.headersource.sqlite",
            "class": "MDS",
            "config": {
                "directory": d + "/small",
                "timezone": "Asia/Shanghai"
            }
        }, "assets": {
            "module": "databroker.assets.sqlite",
            "class": "Registry",
            "config": {"dbpath": d + "/small/assets.sqlite"}
        }
    })

def func_sub(fdic):
    def cb(name, doc):
        if name == "event":
            for k1 in fdic:
                if k1 in doc["data"]:
                    x = doc["data"].pop(k1)
                    for k2, f in fdic[k1]:
                        doc["data"][k2] = f(x)
    return cb

class ImageFiller(CallbackBase):
    def __init__(self):
        super().__init__()
        self.fields = []
        self.datasets = {}
        self.cache = {}

    def descriptor(self, doc):
        for k, v in doc["data_keys"].items():
            if v.get("external") == "FILESTORE:" and k not in self.fields:
                self.fields.append(k)

    def resource(self, doc):
        if doc["spec"] == "AD_HDF5_SWMR" and \
            doc["resource_kwargs"].get("frame_per_point") == 1:
            f = h5py.File(doc["root"] + doc["resource_path"], "r", swmr = True)
            self.datasets[doc["uid"]] = f["entry/data/data"]

    def datum(self, doc):
        d = self.datasets.get(doc["resource"])
        if d:
            self.cache[doc["datum_id"]] = d, doc["datum_kwargs"]["point_number"]

    def event(self, doc):
        for k in self.fields:
            if k in doc["data"]:
                d, i = self.cache.pop(doc["data"][k])
                d.refresh()
                doc["data"][k] = d[i]

    def stop(self, doc):
        for d in self.datasets.values():
            d.file.close()
        for obj in [self.fields, self.datasets, self.cache]:
            obj.clear()

class MyLiveImage(CallbackBase):
    def __init__(self, field):
        super().__init__()
        pyqtgraph.setConfigOptions(imageAxisOrder = "row-major")
        pyqtgraph.mkQApp()
        self.field = field
        self.iv = pyqtgraph.ImageView()
        self.iv.show()

    def event(self, doc):
        self.iv.setImage(numpy.array(doc["data"][self.field]))

@mpl_cb.make_class_safe(logger = mpl_cb.logger)
class LivePlotX(mpl_cb.QtAwareCallback):
    def __init__(
        self, yys, x = None, *, ylabel = None,
        xlim = None, ylim = None, ax = None, **kwargs
    ):
        super().__init__(use_teleporter = kwargs.pop("use_teleporter", None))
        self.__setup_lock = mpl_cb.threading.Lock()
        self.__setup_event = mpl_cb.threading.Event()

        def setup():
            # Run this code in start() so that it runs on the correct thread.
            nonlocal yys, x, xlim, ylim, ax, kwargs
            import matplotlib.pyplot as plt
            with self.__setup_lock:
                if self.__setup_event.is_set():
                    return
                self.__setup_event.set()
            if ax is None:
                ax = plt.subplots()[1]
            self.ax = ax

            self.x = "seq_num" if x is None else \
                mpl_cb.get_obj_fields([x])[0]
            self.yys = [mpl_cb.get_obj_fields(yy) for yy in yys if yy]
            self.ax.set_ylabel(ylabel or "value")
            self.ax.set_xlabel(x or "sequence #")
            if xlim is not None:
                self.ax.set_xlim(*xlim)
            if ylim is not None:
                self.ax.set_ylim(*ylim)
            self.ax.margins(.1)
            self.kwargs = kwargs

        self.__setup = setup

    def start(self, doc):
        self.__setup()
        olines = [l for l in self.ax.lines]
        self.ltitle = "scan_id: %d" % doc["scan_id"]
        self.llms = [[(y, self.ax.plot([], [], **self.kwargs)[0])
            for y in yy] for yy in self.yys]
        [l.remove() for l in olines]
        self.llms = [[
            {y: [l, [], []] for y, l in ll},
            0.0 if len(self.llms) > 1 else -1
        ] for ll in self.llms]
        self.legend()
        super().start(doc)

    def stop(self, doc):
        legend = self.ax.legend(loc = 0, title = self.ltitle)
        try:
            legend.set_draggable(True)
        except AttributeError:
            legend.draggable(True)
        super().stop(doc)

    def event(self, doc):
        d = doc if self.x == "seq_num" else doc["data"]
        try:
            new_x = d[self.x]
        except KeyError:
            return
        [self.update_caches(llm, new_x, doc["data"]) for llm in self.llms]
        self.ax.relim(visible_only = True)
        self.ax.autoscale_view(tight = True)
        self.ax.figure.canvas.draw_idle()
        self.legend()
        super().event(doc)

    def legend(self):
        [[l[0].set_label("%s / %g" % (y, m) if m > 0 else y)
            for y, l in ll.items()] for ll, m in self.llms]
        self.ax.legend(loc = 0, title = self.ltitle)

    @staticmethod
    def update_caches(llm, new_x, data):
        ll = llm[0]
        for y in ll:
            if y not in data:
                continue
            new_y = data[y]
            ll[y][1].append(new_x)
            ll[y][2].append(new_y)
            if llm[1] > -1:
                llm[1] = max(llm[1], abs(new_y))
        m = llm[1] if llm[1] > -1 else 0.0
        for y in ll:
            l = ll[y]
            l[0].set_data(l[1], [y / m for y in l[2]] if m else l[2])

@mpl_cb.make_class_safe(logger = mpl_cb.logger)
class LiveChans(mpl_cb.QtAwareCallback):
    def __init__(self, field, *, columns = 2, use_teleporter = None):
        super().__init__(use_teleporter = use_teleporter)
        self.__setup_lock = mpl_cb.threading.Lock()
        self.__setup_event = mpl_cb.threading.Event()
        def setup():
            # Run this code in start() so that it runs on the correct thread.
            with self.__setup_lock:
                if self.__setup_event.is_set():
                    return
                self.__setup_event.set()
            self.field = mpl_cb.get_obj_fields([field])[0]
            self.columns, self.axes = columns, None
        self.__setup = setup

    def start(self, doc):
        self.__setup()
        super().start(doc)

    def event(self, doc):
        import matplotlib.pyplot as plt
        data = doc["data"].get(self.field)
        if data is None:
            super().event(doc)
            return
        if self.axes is None:
            rows = int(numpy.ceil(data.shape[0] / self.columns))
            fig, self.axes = plt.subplots(rows, self.columns)
            fig.tight_layout()
            self.axes = self.axes.reshape((rows * self.columns,))[:data.shape[0]]
            self.lines = [ax.plot([], [])[0] for ax in self.axes]
        x = list(range(data.shape[1]))
        for ax, l, y in zip(self.axes, self.lines, data):
            l.set_data(x, y)
            ax.relim(visible_only = True)
            ax.autoscale_view(tight = True)
        super().event(doc)

