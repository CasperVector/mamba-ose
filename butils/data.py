import bluesky.callbacks.mpl_plotting as mpl_cb
from databroker.v0 import Broker
from bluesky.callbacks.broker import LiveImage
from bluesky.callbacks.stream import LiveDispatcher

def roi_sum(roi, arr):
	(a, b), roi = roi[0], roi[1:]
	return sum(roi_sum(roi, arr1) for arr1 in arr[a : b]) \
		if roi else sum(arr[a : b])

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

class MyLiveDispatcher(LiveDispatcher):
	def start(self, doc):
		super().start(doc)
		self.my_uid = self._stream_start_uid

class FuncDispatcher(MyLiveDispatcher):
	def __init__(self, fdic):
		self.fdic = fdic
		super().__init__()

	def event(self, doc):
		for k1 in self.fdic:
			if k1 in doc["data"]:
				x = doc["data"].pop(k1)
				for k2, f in self.fdic[k1]:
					doc["data"][k2] = f(x)
		return super().event(doc)

class MyLiveImage(LiveImage):
	update = lambda self, data: super().update(data[0])

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

