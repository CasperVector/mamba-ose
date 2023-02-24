import re
from bluesky import plans
from bluesky import plan_stubs as bps, preprocessors as bpp, progress as bprog

PANDA_FREQ = int(125e6)

def seq_outs_not(l):
	return [f for f in ["out%s%d" % (c, i)
		for i in [1, 2] for c in "abcdef"] if f not in l]

def encoder_monitor(panda, inp):
	if not inp.startswith("inenc"):
		return []
	inp = re.sub(r"\.[^.]+$", "", inp)
	if getattr(panda, inp).dcard_type.value.get() != "Encoder Control":
		return []
	out = inp.replace("in", "out")
	return [
		("%s.%s" % (out, f), ("%s.%s" % (inp, f)).upper())
		for f in ["a", "b", "z", "data", "val"]
	] + [("%s.enable" % out, "ONE")]

def prep_simple(panda, outputs, inputs):
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
			inp = getattr(panda, inp)
			print("%s.motor_drbv - %s.value = %s" %
				(motor.vname(), inp.vname(), inp.bind(motor)))
	panda.configure(cfg)

def seq_disable():
	return {"seq1.repeats": 1, "seq1.table": dict(
		[("trigger", ["Immediate"])] +
		[(f, [1]) for f in ["repeats", "time1", "time2"]] +
		[(f, [0]) for f in ["position"] + seq_outs_not([])]
	)}

def seq_warmup():
	return {"pcap.enable": "ONE", "seq1.repeats": 1, "seq1.table": dict(
		[("trigger", ["Immediate"])] +
		[(f, [1]) for f in ["repeats", "time1", "time2", "outa1"]] +
		[(f, [0]) for f in ["position"] + seq_outs_not(["outa1"])]
	)}

def cfg_simple(panda, motor, lo, hi, num, duty,
	period = None, velocity = None, pad = None):
	inp = panda.motors[motor]
	assert inp == panda.get_input("seq1.posa")
	if period is None:
		if velocity is None:
			velocity = motor.velocity.get()
		else:
			motor.velocity.set(velocity).wait()
		period = abs(hi - lo) / (num + duty - 1.0) / velocity
	elif velocity is None:
		velocity = abs(hi - lo) / (num + duty - 1.0) / period
		motor.velocity.set(velocity).wait()
	else:
		raise ValueError("values given for both period and velocity")
	if pad is None:
		pad = max(0.5, 2 * motor.acceleration.get())
	pad *= velocity
	assert num > 0 and period > 0.0 and velocity > 0.0 and pad > 0.0
	return inp, period, pad

def seq_simple(inp, lo, hi, num, duty, period, pad, snake):
	live, dead = duty * period * PANDA_FREQ, (1.0 - duty) * period * PANDA_FREQ
	assert live >= 1.0 and dead >= 1.0
	if lo > hi:
		pad *= -1
	scale, offset = inp.scale.get(), inp.offset.get()
	lo, hi, pad = (lo - offset) / scale, (hi - offset) / scale, pad / scale
	table = dict([
		("trigger", ["POSA>=POSITION", "POSA>=POSITION",
				"POSA<=POSITION", "POSA<=POSITION"]
			if pad > 0.0 else ["POSA<=POSITION", "POSA<=POSITION",
				"POSA>=POSITION", "POSA>=POSITION"]),
		("position", [lo, hi + pad / 2, hi, lo - pad / 2]),
		("time1", [live, 0, live, 0]), ("time2", [dead, 1, dead, 1]),
		("repeats", [num, 1, num, 1]), ("outa1", [1, 0, 1, 0])
	] + [(f, [0] * 4) for f in seq_outs_not(["outa1"])])
	if not snake:
		table = dict((k, [v[0], v[3]]) for k, v in table.items())
	return {"seq1.repeats": 0, "seq1.table": table}

def grid_cfg(args, pad, div, snake_axes, progress):
	assert not len(args) % 4
	oaxes, pnums = len(args) // 4 - 1, []
	div = [div, oaxes - 1] if isinstance(div, int) else list(div)
	if oaxes:
		assert div[0] >= 0 and 0 <= div[1] < oaxes
		for i in range(div[1], oaxes - 1):
			div[0] *= args[4 * i + 3]
	else:
		assert div[0] in [0, 1]
	div[1] = 1
	for i in range(oaxes):
		div[1] *= args[4 * i + 3]
		pnums.append(args[4 * i + 3])
	if not div[0]:
		div[0] = div[1]
	pnums.append(2)
	if progress:
		progress.bind(bprog.ProgressSimple(pnums))

	lo, hi = args[-3:-1]
	pad1 = -pad if lo > hi else pad
	snaking, scans = plans.grid_scan(
		[], *(args[:-3] + (lo - pad1, hi + pad1, 2)),
		snake_axes = snake_axes, frag = True
	)
	def scan_gen(steps):
		for i in range(steps):
			yield from next(scans)
	return snaking[-1], div, scan_gen

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

def frag_simple(panda, *args, duty, pad = None, div = 0,
	snake_axes = True, period = None, velocity = None, progress = None):
	motor, lo, hi, num = args[-4:]
	inp, period, pad = cfg_simple(panda, motor, lo, hi, num, duty,
		period = period, velocity = velocity, pad = pad)
	snake, div, scan_gen = grid_cfg(args, pad, div, snake_axes, progress)
	seqs = [seq_simple(inp, l, h, num, duty, period, pad, snake)
		for l, h in [(lo, hi), (hi, lo)]]
	seqs.append(seq_disable())
	return grid_frag(seqs, num, snake, div, scan_gen)

def fwrap_adtrig(ads):
	def frag_wrap(scan, *, num_points, **kwargs):
		if num_points:
			for ad in ads:
				yield from bps.configure(ad, {"cam.num_images": num_points})
				yield from bps.configure(ad, {"cam.acquire": 1}, action = True)
		yield from scan
		if num_points:
			for ad in ads:
				yield from bps.configure(ad, {"cam.acquire": 0}, action = True)
				yield from bps.configure(ad, {"cam.num_images": 1})
	return frag_wrap

def fly_frag(panda, adp, dets, frag_gen, frag_wrap = [], md = None):
	if callable(frag_wrap):
		frag_wrap = [frag_wrap]
	@bpp.stage_run_decorator([adp] + dets, md = md)
	def inner():
		armed = False
		yield from bps.configure(panda, {"pcap.enable": "ONE"})
		for seq, kwargs, scan in frag_gen:
			yield from bps.configure(panda, seq)
			if not armed:
				yield from bps.configure\
					(adp, {"cam.acquire": 1}, action = True)
				armed = True
			for fwrap in frag_wrap:
				scan = fwrap(scan, **kwargs)
			yield from scan
	return inner()

