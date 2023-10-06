import re
from bluesky import plans
from bluesky import plan_stubs as bps, preprocessors as bpp
from .bubo import sseq_disable

PANDA_FREQ = int(125e6)

def seq_outs_not(l):
	return [f for f in ["out%s%d" % (c, i)
		for i in [1, 2] for c in "abcdef"] if f not in l]

def encoder_monitor(panda, inp):
	if not inp.startswith("inenc"):
		return []
	inp = re.sub(r"\.[^.]+$", "", inp)
	out = inp.replace("in", "out")
	return [
		("%s.%s" % (out, f), ("%s.%s" % (inp, f)).upper())
		for f in ["a", "b", "z", "data", "val"]
	] + [("%s.enable" % out, "ONE")]

def prep_simple(panda, outputs, inputs, **kwargs):
	cfg = {
		"pcap.enable": "ZERO",
		"pcap.gate": "SEQ1.OUTA",
		"pcap.trig": "SEQ1.OUTA",
		"pcap.trig_edge": "Falling",
		"seq1.enable": "PCAP.ACTIVE"
	}
	cfg.update([(f, "SEQ1.OUTA") for f in outputs])
	for i, (inp, motor) in enumerate(inputs):
		cfg.update(encoder_monitor(panda, inp))
		cfg.update([("%s.capture" % inp, "Min Max Mean")])
		if i < 3:
			cfg.update([("seq1.pos%s" % chr(ord("a") + i), inp.upper())])
		if motor:
			getattr(panda, inp).bind(motor, **kwargs)
	panda.configure(cfg)

def seq_disable(block):
	return {"%s.repeats" % block: 1, "%s.table" % block: dict(
		[("trigger", ["Immediate"])] +
		[(f, [1]) for f in ["repeats", "time1", "time2"]] +
		[(f, [0]) for f in ["position"] + seq_outs_not([])]
	)}

def seq_warmup(block):
	return {"%s.repeats" % block: 1, "%s.table" % block: dict(
		[("trigger", ["Immediate"])] +
		[(f, [1]) for f in ["repeats", "time1", "time2", "outa1"]] +
		[(f, [0]) for f in ["position"] + seq_outs_not(["outa1"])]
	), "pcap.enable": "ONE"}

def velo_simple(motor, lo, hi, num, duty,
	period = None, velocity = None, pad = None):
	if period is None:
		if velocity is None:
			velocity = motor.velocity.get()
		period = abs(hi - lo) / (num + duty - 1.0) / velocity
	elif velocity is None:
		velocity = abs(hi - lo) / (num + duty - 1.0) / period
	else:
		raise ValueError("values given for both period and velocity")
	if pad is None:
		pad = max(0.5, 2 * motor.acceleration.get()) * velocity
	assert num > 0 and period > 0.0 and velocity > 0.0 and pad > 0.0
	return period, velocity, pad

def seq_simple(inp, lo, hi, num, duty, period, pad, snake):
	live, dead = duty * period * PANDA_FREQ, (1.0 - duty) * period * PANDA_FREQ
	assert live >= 1.0 and dead >= 1.0
	if lo > hi:
		pad *= -1
	scale, offset = inp.scale.get(), inp.offset.get()
	lo, hi, pad = (lo - offset) / scale, (hi - offset) / scale, pad / scale
	pos = [(p, inp.root.get_input("seq1.pos%s" % p)) for p in "abc"]
	pos = [p for p, i in pos if i == inp.prefix][0].upper()
	table = dict([
		("trigger", ["POS%s%s=POSITION" % (pos, op)
			for op in (">><<" if pad > 0.0 else "<<>>")]),
		("position", [lo, hi + pad / 2, hi, lo - pad / 2]),
		("time1", [live, 0, live, 0]), ("time2", [dead, 1, dead, 1]),
		("repeats", [num, 1, num, 1]), ("outa1", [1, 0, 1, 0])
	] + [(f, [0] * 4) for f in seq_outs_not(["outa1"])])
	if not snake:
		table = dict((k, [v[0], v[3]]) for k, v in table.items())
	return {"seq1.repeats": 0, "seq1.table": table}

def grid_cfg(args, div, pad, snake_axes):
	assert not len(args) % 4
	oaxes = len(args) // 4 - 1
	div = [div, oaxes - 1] if isinstance(div, int) else list(div)
	if oaxes:
		assert div[0] >= 0 and 0 <= div[1] < oaxes
		for i in range(div[1], oaxes - 1):
			div[0] *= args[4 * i + 3]
	else:
		assert div[0] in [0, 1]
	pnums, div[1] = [], 1
	for i in range(oaxes):
		pnums.append(args[4 * i + 3])
		div[1] *= pnums[-1]
	if not div[0]:
		div[0] = div[1]
	pnums.append(2)
	points = div[1] * args[-1]

	lo, hi = args[-3:-1]
	pad1 = -pad if lo > hi else pad
	snaking, scans = plans.grid_scan(
		[], *(args[:-3] + (lo - pad1, hi + pad1, 2)),
		snake_axes = snake_axes, frag = True
	)
	def scan_gen(steps):
		for i in range(steps):
			yield from next(scans)
	return snaking[-1], div, scan_gen, \
		{"num_points": points, "hints": {"progress": ["simple"] + pnums}}

def grid_frag(seqs, num, snake, div, scan_gen):
	def points_gen():
		rev = 0
		yield seqs[2], 0, 1
		frag = min(div[0], div[1])
		yield seqs[rev], frag * num, frag * 2 - 1
		while True:
			div[1] -= frag
			if not div[1]:
				break
			if snake:
				rev = (div[0] % 2) - rev
			frag = min(div[0], div[1])
			yield seqs[rev], frag * num, frag * 2
	def frag_gen():
		for seq, points, steps in points_gen():
			yield seq, {"num_points": points}, scan_gen(steps)
	return frag_gen()

def fwrap_second(plan):
	second = [True]
	def fwrap(scan, **kwargs):
		yield from scan
		if second[0]:
			yield from plan
			second[0] = False
	return fwrap

def frag_simple(panda, *args, duty, div = 0, snake_axes = True,
	period = None, velocity = None, pad = None):
	motor, lo, hi, num = args[-4:]
	period, velocity, pad = velo_simple(motor, lo, hi, num, duty,
		period = period, velocity = velocity, pad = pad)
	snake, div, scan_gen, md = grid_cfg(args, div, pad, snake_axes)
	seqs = [seq_simple(panda.motors[motor], l, h, num,
		duty, period, pad, snake) for l, h in [(lo, hi), (hi, lo)]]
	seqs.append(seq_disable("seq1"))
	return grid_frag(seqs, num, snake, div, scan_gen), \
		[fwrap_second(bps.configure(motor, {"velocity": velocity}))], md

def fly_frag(panda, adp, devs, frag_gen, fwraps = [], md = None):
	if callable(fwraps):
		fwraps = [fwraps]
	@bpp.stage_run_decorator([adp] + devs, md = md)
	def inner():
		for seq, kwargs, scan in frag_gen:
			yield from bps.configure(panda, seq)
			yield from bps.configure(panda, {"pcap.enable": "ONE"})
			yield from bps.configure(adp, {"cam.acquire": 1}, action = True)
			for fwrap in fwraps:
				scan = fwrap(scan, **kwargs)
			yield from scan
			yield from bps.configure(adp, {"cam.acquire": 0}, action = True)
	return inner()

def fwrap_first(plan):
	first = [True]
	def fwrap(scan, **kwargs):
		if first[0]:
			yield from plan
			first[0] = False
		yield from scan
	return fwrap

def fwrap_config(dets, configs):
	def plan():
		for det in dets:
			cfg = configs.get(det)
			if cfg:
				yield from bps.configure(det, cfg)
	return fwrap_first(plan())

def fwrap_adtrig(ads):
	def fwrap(scan, *, num_points, **kwargs):
		if num_points:
			for ad in ads:
				yield from bps.configure(ad, {"cam.num_images": num_points})
				yield from bps.configure(ad, {"cam.acquire": 1}, action = True)
		yield from scan
		if num_points:
			for ad in ads:
				yield from bps.configure(ad, {"cam.acquire": 0}, action = True)
	return fwrap

def motors_get(args):
	return [args[4 * i] for i in range(len(args) // 4)]

def fly_simple(panda, adp, dets, *args, configs = {}, md = {}, **kwargs):
	frag_gen, fwraps, _md = frag_simple(panda, *args, **kwargs)
	_md.update(md or {})
	return fly_frag(panda, adp, dets + motors_get(args), frag_gen,
		[fwrap_adtrig(dets), fwrap_config(dets, configs)] + fwraps, md = _md)

def sseq_base(scomp):
	def seq(bubo):
		while True:
			msg = bubo.get()
			if msg[0] == "exit" or (scomp(msg) and not bubo.record()):
				return
	return seq

def scomp_pcomp(dev, lo, hi, num, pad, snake):
	assert num > 1 and pad >= 0.0
	sign = -1 if hi < lo else 1
	step = abs(hi - lo) / (num - 1)
	state = [0, 1]
	def pcomp(msg):
		if msg[0] != "input" or msg[1] != dev:
			return False
		if state[0] >= num:
			if snake:
				if sign * (msg[2] - hi) >= pad / 2:
					state[0], state[1] = num - 1, -1
				return False
			else:
				state[0] = -1
		if state[0] < 0:
			if sign * (lo - msg[2]) >= pad / 2:
				state[0], state[1] = 0, 1
			return False
		if (sign * (msg[2] - lo) - state[0] * step) * state[1] >= 0:
			state[0] += state[1]
			return True
		return False
	return pcomp

def sfrag_simple(bubo, *args, div = 0, snake_axes = True, pad = None):
	motor, lo, hi, num = args[-4:]
	bubo.inputs.set([motor.readback]).wait()
	if pad is None:
		pad = max(0.5, 2 * motor.acceleration.get()) * motor.velocity.get()
	snake, div, scan_gen, md = grid_cfg(args, div, pad, snake_axes)
	seqs = [sseq_base(scomp_pcomp(motor.readback, l, h, num, pad, snake))
		for l, h in [(lo, hi), (hi, lo)]]
	seqs.append(sseq_disable)
	return grid_frag(seqs, num, snake, div, scan_gen), md

def sfly_frag(bubo, devs, frag_gen, fwraps = [], md = None):
	if callable(fwraps):
		fwraps = [fwraps]
	bubo.outputs.set(devs).wait()
	@bpp.stage_run_decorator([bubo] + devs, md = md)
	def inner():
		for seq, kwargs, scan in frag_gen:
			yield from bps.configure(bubo, {"seq": seq}, action = True)
			yield from bps.configure(bubo, {"enable": 1}, action = True)
			for fwrap in fwraps:
				scan = fwrap(scan, **kwargs)
			yield from scan
			yield from bps.configure(bubo, {"enable": 0}, action = True)
	return inner()

def sfly_simple(bubo, dets, *args, md = {}, **kwargs):
	frag_gen, _md = sfrag_simple(bubo, *args, **kwargs)
	_md.update(md or {})
	return sfly_frag(bubo, dets + motors_get(args), frag_gen, md = _md)

