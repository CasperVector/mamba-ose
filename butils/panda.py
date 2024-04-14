import collections
import numpy
import queue
import threading
import time
from ophyd import Component, Device, Signal, Kind
from ophyd.utils.epics_pvs import data_type, data_shape
from .common import fn_wait
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
    n, = set(len(l) for l in data)
    ret = numpy.zeros((max(f.bits_hi for f in fields) // 32 + 1,
        n), dtype = "uint32")
    for f, l in zip(fields, data):
        if f.labels:
            l = [f.labels.index(x) for x in l if isinstance(x, str)]
        l = numpy.array(l, dtype =
            "int32" if f.signed else "uint32").view("uint32")
        i, = {f.bits_lo // 32, f.bits_hi // 32}
        ret[i] |= (l & (2 ** (f.bits_hi - f.bits_lo + 1) - 1)) \
            << (f.bits_lo % 32)
    return list(ret.T.reshape((-1,)))

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
        i, = {f.bits_lo // 32, f.bits_hi // 32}
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
        if typ == "float":
            kwargs["rtolerance"] = 1e-9
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

def panda_posout_bind(obj, bind, motor, **kwargs):
    motors = obj.root.motors
    if obj.motor:
        motors.pop(obj.motor)
    if motor:
        assert motor not in motors
        motors[motor] = obj
    bind(obj, motor, **kwargs)
    obj.motor = motor

def panda_posout_calib(obj, setp, run):
    if obj.rep:
        setp(obj.motor.motor_rep.get())
    rep = obj.value.get()
    if run:
        obj.motor.set_current_position\
            (rep * obj.scale.get() + obj.offset.get())
    return int((obj.motor.readback.get() - obj.offset.get())
        / obj.scale.get()) - rep

def panda_inenc_bind(obj, motor, rep = True):
    obj.rep = rep
    if motor:
        motor.offset_freeze_switch.set(1).wait()
        obj.scale.put(motor.motor_eres.get() *
            (-1 if motor.offset_dir.get() else 1))
        obj.offset.put(motor.offset.get())
    else:
        obj.scale.put(1.0)
        obj.offset.put(0.0)

def panda_inenc_postinit(obj):
    f = obj.val
    f.motor = None
    f.bind = lambda motor, **kwargs: \
        panda_posout_bind(f, panda_inenc_bind, motor, **kwargs)
    f.calibrate = (lambda run = True:
        panda_posout_calib(f, obj.setp.value.put, run))

pandaPostInit = {"inenc": panda_inenc_postinit}

class PandaBlock(Device):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "_post_init"):
            self._post_init()

def seq_outs_not(l):
    return [f for f in ["out%s%d" % (c, i)
        for i in [1, 2] for c in "abcdef"] if f not in l]

def table_disable():
    return dict(
        [("trigger", ["Immediate"])] +
        [(f, [1]) for f in ["repeats", "time1", "time2"]] +
        [(f, [0]) for f in ["position"] + seq_outs_not([])]
    )

def seq_disable(block):
    return {"%s.repeats" % block: 1, "%s.table" % block: table_disable()}

class PandaDseqEnable(Signal):
    def put(self, val):
        if not self._readback and val:
            self.parent._stage()
        elif self._readback and not val:
            self.parent._q0.put(("exit",))
        super().put(1 if val else 0)

class PandaDseqPoll(Signal):
    def put(self, val):
        if val:
            for i in range(int(self.root._poll_period[1] /
                self.parent._poll_period)):
                if self.root.pcap.active.value.get():
                    break
                time.sleep(self.parent._poll_period)
            else:
                super().put(0)
                return
        super().put(1 if val else 0)

class PandaDseqTables(Signal):
    def put(self, tables):
        for table in tables:
            self.parent._q0.put(("table", table))
        super().put("")

    def set(self, tables, **kwargs):
        if not isinstance(tables, list):
            tables = [tables]
        val = [panda_table_fmt_alt(self.parent._fields, table)
            if table is not None else [] for table in tables]
        return super().set(val, **kwargs)

    def _set_and_wait(self, value, timeout, **kwargs):
        self.put(value)

class PandaDseq(Device):
    _poll_period = 0.01
    state = Component(Signal, value = "idle", kind = "normal")
    counter = Component(Signal, value = 0, kind = "normal")
    enable = Component(PandaDseqEnable, value = 0, kind = "config")
    poll = Component(PandaDseqPoll, value = 0, kind = "omitted")
    tables = Component(PandaDseqTables, value = "", kind = "omitted")

    def __init__(self, *args, fields, **kwargs):
        super().__init__(*args, **kwargs)
        self.state._metadata["write_access"] = False
        self.counter._metadata["write_access"] = False
        self._q0 = self._q1 = self._subs = None
        self._fields, self._end = fields, False
        self._idx, self._max = 0, -1

    def make_cfg(self):
        ret = {
            "pcap.enable": "ZERO",
            "pcap.trig_edge": "Falling",
            "seq1.enable": "SRGATE1.OUT",
            "seq2.enable": "SRGATE2.OUT",
            "lut7.func": "A&~B",
            "lut8.func": "A&~B",
            "lut7.inpa": "PCAP.ACTIVE",
            "lut8.inpa": "PCAP.ACTIVE",
            "lut7.inpb": "SEQ2.ACTIVE",
            "lut8.inpb": "SEQ1.ACTIVE",
            "srgate1.enable": "ZERO",
            "srgate2.enable": "ZERO",
            "srgate1.set_": "LUT7.OUT",
            "srgate2.set_": "LUT8.OUT",
            "srgate1.set_edge": "Rising",
            "srgate2.set_edge": "Rising",
            "srgate1.when_disabled": "Set output low",
            "srgate2.when_disabled": "Set output low"
        }
        ret.update(seq_disable("seq1"))
        ret.update(seq_disable("seq2"))
        return ret

    def max_rows(self):
        return self.root.seq1.table.max_length._readback // \
            (max(f.bits_hi for f in self._fields.values()) // 32 + 1)

    def _stage(self):
        # This also ensures the latest state of these values is retrieved,
        # preventing spurious edges (note each value gets queried twice)
        # appearing on the later subscriptions because of an untimely poll.
        assert not any(block.active.value.get() or block.active.value.get()
            for block in [self.root.seq1, self.root.seq2, self.root.pcap])
        Signal.put(self.poll, 0)
        Signal.put(self.counter, 0, force = True)
        Signal.put(self.state, "run", force = True)
        table = table_disable()
        self.root.configure({
            "seq1.table": table,
            "seq2.table": table,
            "srgate1.enable": "ONE",
            "srgate2.enable": "ONE",
            "srgate1.force_set": "",
            "srgate2.force_set": ""
        }, action = True)
        self._q0, self._q1 = queue.Queue(), collections.deque()
        self._subs = [block.active.value.subscribe((lambda i: (
            lambda *, value, old_value, **kwargs:
            not value and old_value and self._q0.put(("inactive", i))
        ))(i)) for i, block in enumerate([self.root.seq1, self.root.seq2])]
        self._subs.append(self.root.pcap.active.value.subscribe(
            lambda *, value, old_value, **kwargs:
            value and not old_value and self._q0.put(("inactive", -1))
        ))
        self._end, self._idx, self._max = False, 0, -1
        threading.Thread(target = self._run, daemon = True).start()

    def _unstage(self, ret):
        if self._subs:
            for sub, block in zip(self._subs, [
                self.root.seq1, self.root.seq2, self.root.pcap
            ]):
                block.active.value.unsubscribe(sub)
        self.root.configure({"srgate1.enable": "ZERO", "srgate2.enable": "ZERO"})
        Signal.put(self.state, ret, force = True)
        Signal.put(self.poll, 0)
        Signal.put(self.enable, 0)
        self._q0 = self._q1 = None

    def _run(self):
        try:
            while self.counter.get() < self._max or self._max < 0:
                msg = self._q0.get()
                if msg[0] == "exit":
                    break
                elif msg[0] == "table":
                    self._fill0(msg[1])
                elif msg[0] == "inactive":
                    self._fill1(msg[1])
            self._unstage("idle")
        except:
            self._unstage("error")
            raise

    def _fill(self, table):
        if not table:
            self._max = self._idx
            return
        i = self._idx % 2
        getattr(self.root, "srgate%d" % (1 + i)).force_rst.value.put("")
        getattr(self.root, "seq%d" % (1 + i)).table.value.put(table)
        self._idx += 1

    def _fill0(self, table):
        assert not self._end
        if not table:
            self._end = True
        if self._idx:
            self._q1.append(table)
        else:
            self._fill(table)

    def _fill1(self, i):
        if i < 0:
            assert self._idx == 1
        else:
            n = self.counter.get()
            assert i >= 0 and n % 2 == i
            Signal.put(self.counter, n + 1, force = True)
        i = self._idx % 2
        if self._max < 0:
            self._fill(self._q1.popleft())
        if self._max < 0 or self.counter.get() < self._max - 1:
            assert getattr(self.root, "seq%d" % (2 - i)).active.value.get()

class PandaRoot(Device):
    _poll_period = (1.0, 0.1)

    def __init__(self, client, *, name, omcs, **kwargs):
        self._client = client
        super().__init__(name = name, **kwargs)
        self.motors = {}
        self._romits, self._muxes, self._caps = \
            [[getattr(self, a) for a in l] for l in omcs]
        self._poll_active, self._poll_event = False, threading.Event()
        self.pcap.active.value.subscribe(lambda *, value, old_value, **kwargs:
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
        assert fn_wait([a.get for a in self._romits])

    def _start_poll(self):
        def poll():
            self._poll_active = True
            while True:
                try:
                    self._poll_event.wait\
                        (self._poll_period[self.pcap.active.value._readback])
                    self._poll_event.clear()
                    self._update()
                except:
                    self._poll_active = False
                    raise
        threading.Thread(target = poll, daemon = True).start()

    def clear_muxes(self):
        assert fn_wait\
            ([(lambda a: lambda: a.put("ZERO"))(a) for a in self._muxes])

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
        return getattr(self, mux).value.get()

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

    def read_configuration(self, dot = False,
        fast = False, active_extra = ["system"]):
        if fast and not dot and self._config_cache is not None:
            return self._config_cache[int(not dot)].copy()
        ret = self.desc_or_read\
            ("read_configuration", Kind.config, dot, active_extra)
        self._config_cache = ret, collections.OrderedDict\
            ((k.replace(".", "_"), ret[k]) for k in ret)
        return self._config_cache[int(not dot)].copy()

    def configure(self, cfg, action = False, fast = True):
        return super().configure(cfg, action = action, fast = fast)

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

def PandaDevice(hostname = "localhost",
    port = 8888, *, name, inherit = None, **kwargs):
    if not inherit:
        inherit = PandaRoot,
    client = PandABlocksClient(hostname, port)
    client.start()
    capbits = client.get_pcap_bits_fields()
    fclasses, blocks, omcd = panda_fclasses(), [], {}
    sfields = None

    for k, v in client.get_blocks_data().items():
        block, romits, muxcaps = [], [], ([], [])
        for kk, vv in v.fields.items():
            cls, mode, enums, romit, (table, bits, mux, out) = \
                fclasses[(vv.field_type, vv.field_subtype)]
            values = {}
            if table:
                values["fields"] = client.get_table_fields\
                    (k + "1" if v.number > 1 else k, kk)
                if k == "SEQ":
                    sfields = values["fields"]
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
    return type("PandaDevice", inherit, dict(
        [(k.lower(), Component(block, k)) for k, block in blocks] +
        [("dseq", Component(PandaDseq, fields = sfields))]
    ))(client, name = name, omcs = omcs, **kwargs)

