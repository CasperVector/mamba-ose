import collections
import numpy
import threading
from ophyd import Component, Device, Signal, Kind
from ophyd.utils.epics_pvs import data_type, data_shape
from .panda_client import PandABlocksClient

pandaFields = [
	("table", [
		("", "rw", "table", "config"),
		("max_length", "r", "uint", "omitted"),
		("length", "r", "uint", "omitted"),
		("fields", "r", "fields", "omitted")
	]), ("time", [
		("", "rw", "float", "config"),
		("units", "rw", "enum", "config"),
		("raw", "rw", "uint", "omitted"),
		("min", "r", "float", "omitted")
	]), ("bit_mux", [
		("", "rw", "enum", "config"),
		("delay", "rw", "uint", "config"),
		("max_delay", "r", "uint", "omitted")
	]), ("bit_out", [
		("", "r", "bit", "normal"),
		("capture_word", "r", "str", "omitted"),
		("offset", "r", "uint", "omitted")
	]), ("pos_mux", [
		("", "rw", "enum", "config")
	]), ("pos_out", [
		("", "r", "int", "normal"),
		("capture", "rw", "enum", "config"),
		("units", "rw", "str", "config"),
		("scale", "rw", "float", "config"),
		("offset", "rw", "float", "config"),
		("scaled", "r", "float", "omitted")
	])
]
pandaFields = dict(((f, ""), attrs) for f, attrs in pandaFields)

pandaSubs = dict((k, (k, [])) for k in
	["action", "enum", "bit", "int", "timestamp", "samples"])
pandaSubs.update({
	"uint": ("uint", [("max", "r", "uint", "omitted")]),
	"lut": ("str", [("raw", "r", "str", "omitted")]),
	"time": ("float", [
		("units", "rw", "enum", "config"),
		("raw", "rw", "uint", "omitted")
	]), "scalar": ("float", [
		("units", "r", "str", "omitted"),
		("scale", "r", "float", "omitted"),
		("offset", "r", "float", "omitted"),
		("raw", "r", "int", "omitted")
	]), "bits": ("", [("bits", "r", "bits", "omitted")])
})

pandaTypFields = [
	("param", "rw", "config",
		["enum", "bit", "int", "uint", "lut", "time"]),
	("read", "r", "normal",
		["enum", "bit", "int", "uint", "scalar"]),
	("write", "w", "omitted",
		["action", "enum", "bit", "int", "uint"])
]
pandaFields.update((
	(k, typ), [("", mode, pandaSubs[typ][0], kind)] + pandaSubs[typ][1]
) for k, mode, kind, typs in pandaTypFields for typ in typs)

pandaExtFields = [
	("ext_out", ["timestamp", "samples", "bits"],
		[("capture", "rw", "enum", "config")])
]
pandaFields.update(((k, ext), attrs + pandaSubs[ext][1])
	for k, exts, attrs in pandaExtFields for ext in exts)

def panda_table_fmt(fields, data):
	n, = list(set(len(l) for l in data))
	ret = numpy.zeros((max(f.bits_hi for f in fields) // 32 + 1,
		n), dtype = "uint32")
	for f, l in zip(fields, data):
		if f.labels:
			l = [f.labels.index(x) for x in l if isinstance(x, str)]
		l = numpy.array(l, dtype =
			"int32" if f.signed else "uint32").view("uint32")
		i, = list({f.bits_lo // 32, f.bits_hi // 32})
		ret[i] |= (l & (2 ** (f.bits_hi - f.bits_lo + 1) - 1)) \
			<< (f.bits_lo % 32)
	return list(ret.T.flatten())

def panda_table_fmt_alt(fields, val):
	val = [val[k.lower()] for k in fields] \
		if isinstance(val, dict) else list(val)
	if not all(isinstance(x, int) for x in val):
		val = panda_table_fmt(fields.values(), val)
	return val

def panda_table_unfmt(fields, data):
	ret, m = [], max(f.bits_hi for f in fields) // 32 + 1
	data = numpy.array(data, dtype = "uint32").reshape((len(data) // m, m)).T
	for f in fields:
		i, = list({f.bits_lo // 32, f.bits_hi // 32})
		l = (data[i] >> (f.bits_lo % 32)) & \
			(2 ** (f.bits_hi - f.bits_lo + 1) - 1)
		l = list(l.view("int32" if f.signed else "uint32"))
		if f.labels:
			m = len(f.labels)
			l = [f.labels[i] if i < m else i for i in l]
		ret.append(l)
	return ret

def panda_attr_put(obj, val):
	return obj._client.set_field(obj._block, obj._field, val)

def panda_table_put(obj, val):
	return obj._client.set_table(obj._block, obj._field, val)

def panda_attr_get(obj):
	return obj._client.get_field(obj._block, obj._field)

def panda_table_parse(ss):
	return [int(s) for s in ss]

class PandaAttr(Signal):
	def __init__(self, target, *, mode, typ, **kwargs):
		super().__init__(**kwargs)
		self._client = self.root._client
		self._block, self._field = target.split(".", 1)
		self.enum_strs = tuple()
		if typ == "table":
			attr_put, orig_set = panda_table_put, self.set
			self.set = lambda val, **kwargs: \
				orig_set(panda_table_fmt_alt
					(self.parent.fields._readback, val), **kwargs)
		else:
			attr_put = panda_attr_put
		def put(val):
			attr_put(self, val)
			super(PandaAttr, self).put(val)
		self.put = put

		if "r" in mode:
			self._parse = {
				"bit": int, "int": int, "uint": int, "float": float,
				"enum": str, "str": str, "table": panda_table_parse
			}.get(typ)
			if self._parse:
				self._update = lambda val: \
					super(PandaAttr, self).put(self._parse(val))
				def get():
					val = self._parse(panda_attr_get(self))
					super(PandaAttr, self).put(val)
					return val
				self.get = get
		else:
			self._readback = \
				{"action": "", "enum": "", "bit": 0, "int": 0, "uint": 0}[typ]

	def describe(self, dot = False):
		ret = {
			"source": "PANDA:%s.%s" % (self._block, self._field),
			"dtype": data_type(self._readback),
			"shape": data_shape(self._readback)
		}
		if self.enum_strs:
			ret["enum_strs"] = self.enum_strs
		return {self.vname(dot): ret}

class PandaField(Device):
	def __init__(self, prefix, *, mode, elabs, values, **kwargs):
		super().__init__(prefix, **kwargs)
		if hasattr(self, "value"):
			self.value.name = self.name
			if "w" in mode:
				self.set = lambda val, **kwargs: self.value.set(val, **kwargs)
		enums, labels = elabs
		if enums or labels:
			enum, = enums
			getattr(self, enum).enum_strs = tuple(labels)
		for k, v in values.items():
			getattr(self, k)._readback = v

def panda_posout_bind(obj, bind, motor):
	motors = obj.root.motors
	if obj.motor:
		motors.pop(obj.motor)
	if motor:
		assert motor not in motors
		bind(obj, motor)
		motors[motor] = obj
	obj.motor = motor
	return obj.calibrate(False) if motor else None

def panda_posout_calib(obj, setp, run):
	raw = int(1.0 / obj.scale.get() *
		(obj.motor.readback.get() - obj.offset.get()))
	if run:
		setp(raw)
	return raw - obj.value.get()

def panda_inenc_bind(obj, motor):
	obj.scale.put(motor.motor_eres.get() *
		(-1 if motor.offset_dir.get() else 1))
	obj.offset.put(motor.offset.get())

def panda_inenc_postinit(obj):
	f = obj.val
	f.motor = None
	f.bind = lambda motor: panda_posout_bind(f, panda_inenc_bind, motor)
	f.calibrate = (lambda run = True:
		panda_posout_calib(f, obj.setp.value.put, run))

pandaPostInit = {"inenc": panda_inenc_postinit}

class PandaBlock(Device):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if hasattr(self, "_post_init"):
			self._post_init()

class PandaRoot(Device):
	def __init__(self, client, *, name, omcs, period = (1.0, 0.1), **kwargs):
		self._client = client
		super().__init__(name = name, **kwargs)
		self.motors = {}
		self._romits, self._muxes, self._caps = \
			[[getattr(self, a) for a in l] for l in omcs]
		self._period, self._polling = period, False
		self._poll_event = threading.Event()
		self.pcap.active.value.subscribe(lambda value, old_value, **kwargs:
			value and not old_value and self._poll_event.set())
		self._update()
		self._update_romits()
		self._start_poll()

	def _update(self):
		for k, v in self._client.get_changes():
			if k[0] == "*":
				continue
			k = k.lower().split(".")
			if len(k) != 3:
				assert len(k) == 2
				k.append("value")
			k[1] = panda_field_fmt(k[1])
			getattr(self, ".".join(k))._update(v)

	def _update_romits(self):
		for a in self._romits:
			a.get()

	def _start_poll(self):
		def poll():
			self._polling = True
			while True:
				try:
					self._poll_event.wait\
						(self._period[self.pcap.active.value._readback])
					self._poll_event.clear()
					self._update()
				except:
					self._polling = False
					raise
		threading.Thread(target = poll, daemon = True).start()

	def clear_muxes(self):
		for a in self._muxes:
			a.put("ZERO")

	def clear_capture(self):
		assert self._client.send_recv("*CAPTURE=\n") == "OK"

	def active_blocks(self):
		ret = set()
		for a in self._muxes:
			val = a._readback
			if val not in ["ZERO", "ONE"]:
				ret.add(val.lower().split(".")[0])
				ret.add(a._block.lower())
		for a in self._caps:
			if a._readback != "No":
				ret.add("pcap")
				ret.add(a._block.lower())
		return ret

	def get_input(self, mux):
		return getattr(self, getattr(self, mux).value.get().lower())

	def desc_or_read(self, op, kind, dot, active_extra):
		ret = collections.OrderedDict()
		active = None if active_extra is None else \
			self.active_blocks() | set(active_extra)
		for name, cpt in self._get_components_of_kind(kind):
			if active is None or name in active:
				ret.update(getattr(cpt, op)(dot))
		return ret

	def describe_configuration(self, dot = False, active_extra = ["system"]):
		return self.desc_or_read\
			("describe_configuration", Kind.config, dot, active_extra)

	def read_configuration(self, dot = False, active_extra = ["system"]):
		return self.desc_or_read\
			("read_configuration", Kind.config, dot, active_extra)

def panda_typ_fmt(s):
	return s.replace("_", "").title()

def panda_field_fmt(s):
	return "set_" if s == "set" else s

def panda_fclasses():
	ret = {}
	for f, attrs in pandaFields.items():
		attrs = [
			(a[0] if a[0] else "value",
			"." + a[0].upper() if a[0] else "") + a[1:]
			for a in attrs
		]
		cls = type(
			"PandaField" + panda_typ_fmt(f[0]) + panda_typ_fmt(f[1]),
			(PandaField,), dict((a[0], Component(
				PandaAttr, a[1], mode = a[2], typ = a[3], kind = a[4]
			)) for a in attrs)
		)

		mode = [a[2] for a in attrs if not a[1]]
		mode = mode[0] if mode else ""
		enums = [a[0] for a in attrs if a[3] == "enum"]
		romit = [a[0] for a in attrs if a[4] == "omitted" and "r" in a[2]]
		tbmo = (f[0] == "table", f[1] == "bits",
			f[0] in ["bit_mux", "pos_mux"], f[0] in ["pos_out", "ext_out"])
		ret[f] = cls, mode, enums, romit, tbmo
	return ret

def PandaDevice(hostname = "localhost", port = 8888, *, name, **kwargs):
	client = PandABlocksClient(hostname, port)
	client.start()
	capbits = client.get_pcap_bits_fields()
	fclasses, blocks, omcd = panda_fclasses(), [], {}

	for k, v in client.get_blocks_data().items():
		block, romits, muxcaps = [], [], ([], [])
		for kk, vv in v.fields.items():
			cls, mode, enums, romit, (table, bits, mux, out) = \
				fclasses[(vv.field_type, vv.field_subtype)]
			values = {}
			if table:
				values["fields"] = client.get_table_fields\
					(k + "1" if v.number > 1 else k, kk)
			if bits:
				values["bits"] = capbits["%s.%s.CAPTURE" % (k, kk)]

			f = panda_field_fmt(kk.lower())
			block.append((f, Component(cls, "." + kk,
				mode = mode, elabs = (enums, vv.labels), values = values)))
			romits.extend("%s.%s" % (f, r) for r in romit)
			for l, b, a in zip(muxcaps, (mux, out), ("value", "capture")):
				if b:
					l.append("%s.%s" % (f, a))
		omcd[k] = (romits,) + muxcaps
		if k.lower() in pandaPostInit:
			block.append(("_post_init", pandaPostInit[k.lower()]))
		block = type("PandaBlock" + panda_typ_fmt(k),
			(PandaBlock,), dict(block))
		blocks.append((k, v.number, block))

	idxs = lambda n: ["%d" % (i + 1) for i in range(n)] if n > 1 else [""]
	omcs = [
		["%s%s.%s" % (k.lower(), idx, a) for k, n, block in blocks
		for idx in idxs(n) for a in omcd[k][i]] for i in range(3)
	]
	blocks = [(k + idx, block) for k, n, block in blocks for idx in idxs(n)]
	return type("PandaDevice", (PandaRoot,), dict(
		(k.lower(), Component(block, k)) for k, block in blocks
	))(client, name = name, omcs = omcs, **kwargs)

