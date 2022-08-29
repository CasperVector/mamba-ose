import cv2
import numpy
from mamba.backend.zserver import raise_syntax, unary_op
from .common import img_phist, AttiAdMixin

QUARTER_BINS = 90

def img_origin(img, threshold):
    img = cv2.GaussianBlur(img, (0, 0), cv2.BORDER_DEFAULT)
    pixels = img > threshold
    pixels = numpy.nonzero(pixels) + (img[pixels],)
    total = pixels[2].sum()
    return (pixels[1] * pixels[2]).sum() / total, \
        (pixels[0] * pixels[2]).sum() / total

def img_eval(img, origin):
    if not img.any():
        img = numpy.zeros((2, 2))
        img[0, 0] = 1
    hist = img_phist(img, origin, (0, 4 * QUARTER_BINS))[0]
    hist = hist.reshape((4, QUARTER_BINS)) * (4 * QUARTER_BINS / hist.sum())
    quad = hist.sum(1)
    return (quad[0] + quad[3]) - (quad[1] + quad[2]), \
        (quad[0] + quad[1]) - (quad[2] + quad[3]), hist.std()

class GradOptim(object):
    ratios = 4, 3

    def __init__(self, xlimits, ylimits):
        assert len(xlimits) == len(ylimits)
        self.xlimits, self.ylimits = xlimits, ylimits
        self.xs = self.grad = self.ds = self.ys = \
            self.best = self.converge = None

    def start(self, xs0):
        assert len(xs0) == len(self.xlimits)
        self.xs, self.grad = xs0, [None] * len(xs0)
        self.ds, self.ys, self.best, self.converge = None, None, None, None

    def step(self, ys, xs = None):
        if any(abs(y) > ymax for y, (yend, ymax) in zip(ys, self.ylimits)):
            raise RuntimeError("Output vector gone out of range")
        elif all(abs(y) < yend for y, (yend, ymax) in zip(ys, self.ylimits)):
            return
        first = self.best is None
        best = numpy.prod([max(abs(y) / yend, 1)
            for y, (yend, ymax) in zip(ys, self.ylimits)])
        if first or best < self.best:
            self.best = best
            self.converge = 1
        else:
            self.converge += 1
            if self.converge >= self.ratios[1] * len(self.grad):
                return
        return self.diff(first, ys, xs)

    def diff(self, first, ys, xs):
        if first:
            self.ds = [
                (xmin - x if x < (xmin + xmax) / 2 else xmax - x) \
                    / self.ratios[0]
                for x, (xmin, xmax) in zip(self.xs, self.xlimits)
            ]
        else:
            for i, (d, y) in enumerate(zip(self.ds, self.ys)):
                if d:
                    self.grad[i] = (ys[i] - y) / d
            ds = [-y / g if g else 0.0 for y, g in zip(ys, self.grad)]
            ds = [(i, d) for i, d in enumerate(ds) if d]
            if ds:
                i, d = sorted(ds, key = lambda e: abs(e[1]))[-1]
                if d:
                    self.ds = [0.0] * len(self.grad)
                    self.ds[i] = d
        self.xs = [x + d for x, d in zip(self.xs, self.ds)]
        self.ys = ys
        if not all(xmin <= x <= xmax
            for x, (xmin, xmax) in zip(self.xs, self.xlimits)):
            raise RuntimeError("Input vector gone out of range")
        return self.xs

class AttiXes(AttiAdMixin):
    def configure(self, ad, motors, threshold, ylimits, xlimits = None):
        assert int(ad.hdf1.ndimensions.get()) == len(motors) == 2
        if not xlimits:
            xlimits = [(m.low_limit_travel.get(), m.high_limit_travel.get())
                for m in motors]
            xlimits = [(0.9 * lo + 0.1 * hi, 0.1 * lo + 0.9 * hi)
                for lo, hi in xlimits]
        self.ad, self.motors, self.threshold = ad, motors, threshold
        self.devices = [self.ad] + self.motors
        self.optim = GradOptim(xlimits, ylimits)

    def move(self, xs):
        [s.wait() for s in [m.set(x) for m, x in zip(self.motors, xs)]]

    def refresh(self):
        assert self.dataset, "need stage()"
        doc, img = self.acquire()
        doc["data"]["origin"] = img_origin(img, self.threshold)
        doc["data"]["eval"] = img_eval(img, doc["data"]["origin"])
        self.send_event(doc)
        return doc["data"]["eval"] + doc["data"]["origin"]

    def auto_tune(self):
        self.optim.start([m.position for m in self.motors])
        while True:
            ev = self.refresh()
            xs = self.optim.step(ev[:2], [m.position for m in self.motors])
            if not xs:
                break
            self.move(xs)
        return ev

def mzs_xes(self, req):
    op, state = unary_op(req), self.get_state(req)
    if op == "names":
        return {"err": "", "ret": [state.ad.name + "_image"] +
            [m.name for m in state.motors]}
    raise_syntax(req)

def state_build(U, config, name):
    setattr(U, name, AttiXes(U.mzcb))

def saddon_xes(arg):
    name = arg or "atti_xes"
    return {"mzs": {name: mzs_xes},
        "state": lambda U, config: state_build(U, config, name)}

