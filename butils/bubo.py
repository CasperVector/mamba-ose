import queue
import re
import threading
import time
from ophyd import Component, Device, Signal
from ophyd.status import Status
from ophyd.areadetector.filestore_mixins import new_short_uid

sseq_disable = lambda bubo: time.sleep(0.1)

class BuboBubo(object):
	def __init__(self):
		self.seq = sseq_disable
		self.fp = self.q = self.fields = None
		self.inputs, self.outputs, self.roots = [], [], []

	def put(self, *msg):
		q = self.q
		if q:
			q.put(msg)

	def get(self):
		return self.q.get()

	def legend(self):
		self.fp.write("time%s\n" % "".join("," + o.name for o in self.outputs))
		self.fp.flush()

	def record(self):
		for r in self.roots:
			r.trigger().add_callback\
				((lambda r: lambda s: self.put("trigger", r, s))(r))
		roots = set(self.roots)
		while roots:
			msg = self.get()
			if msg[0] == "exit":
				return False
			if msg[0] == "trigger":
				roots.remove(msg[1])
				msg[2].wait()
		# Insertion order preserved by dict() since Python 3.6.
		data = {}
		for o in self.outputs:
			data.update(o.read())
		if self.fields is None:
			self.fields = list(data.keys())
			self.fp.write("time%s\n" % "".join("," + f for f in self.fields))
		self.fp.write("%s%s\n" % (time.time(),
			"".join(",%s" % data[f]["value"] for f in self.fields)))
		self.fp.flush()
		return True

	def bind(self, seq = None, inputs = None, outputs = None):
		assert not self.q
		if seq is not None:
			self.seq = seq
		if inputs is not None:
			self.inputs = inputs
		if outputs is not None:
			self.outputs, self.roots = outputs, []
			for d in outputs:
				if d.root not in self.roots:
					self.roots.append(d.root)

	def capture(self, record):
		assert not self.q
		if self.fp:
			self.fp.close()
			self.fp = None
		if record:
			self.fp = open(record, "w")
			self.fields = None

	def start(self):
		assert self.fp and not self.q
		status, self.q = Status(self), queue.Queue()
		subs = [(i, i.subscribe((lambda i:
			lambda *, value, **kwargs:
			value is not None and self.put("input", i, value)
		)(i))) for i in self.inputs]
		def unsubscribe():
			for i, sub in subs:
				i.unsubscribe(sub)
		def seq():
			exc = None
			for fn in [(lambda: self.seq(self)), unsubscribe]:
				try:
					fn()
				except Exception as e:
					if not exc:
						exc = e
			self.q = None
			if exc:
				status.set_exception(exc)
				raise exc
			else:
				status.set_finished()
		threading.Thread(target = seq, daemon = True).start()
		return status

	def abort(self):
		self.put("exit")

class BuboBind(Signal):
	def __init__(self, param, **kwargs):
		super().__init__(**kwargs)
		self._param = param

	def put(self, val):
		self.root._bubo.bind(**{self._param: val})
		super().put(self.get())

	def get(self):
		return getattr(self.root._bubo, self._param)

	def describe(self, dot = False):
		return {self.vname(dot): {"type": "special", "shape": [],
			"source": "BUBO:bind.%s" % self._param}}

class BuboCapture(Signal):
	def put(self, val):
		if not val:
			self.root.enable.set(0, timeout = 1.0).wait()
		self.root._bubo.capture(self.root.full_path if val else "")
		super().put(self.get())

	def get(self):
		return int(self.root._bubo.fp is not None)

	def describe(self, dot = False):
		return {self.vname(dot):
			{"type": "integer", "shape": [], "source": "BUBO:capture"}}

class BuboEnable(Signal):
	_val = 0

	def _finish_cb(self, status):
		self._val = 0
		super().put(0)

	def put(self, val):
		if not self._val and val:
			self._val = 1
			self.root._bubo.start().add_callback(self._finish_cb)
		elif self._val and not val:
			self.root._bubo.abort()
		super().put(self.get())

	def get(self):
		return self._val

	def describe(self, dot = False):
		return {self.vname(dot):
			{"type": "integer", "shape": [], "source": "BUBO:enable"}}

class BuboDevice(Device):
	seq, inputs, outputs = [Component(BuboBind, name, kind = "omitted") \
		for name in ["seq", "inputs", "outputs"]]
	capture = Component(BuboCapture, kind = "omitted")
	enable = Component(BuboEnable, kind = "omitted")
	write_dir, full_path = "/", ""

	def __init__(self, **kwargs):
		self._bubo = BuboBubo()
		super().__init__(**kwargs)

	def stage(self):
		super().stage()
		self.full_path = "%s/%s.csv" % \
			(re.sub("/+$", "", self.write_dir), new_short_uid())
		self.capture.set(1, timeout = 1.0).wait()

	def unstage(self):
		self.capture.set(0, timeout = 1.0).wait()
		self.full_path = ""
		super().unstage()

