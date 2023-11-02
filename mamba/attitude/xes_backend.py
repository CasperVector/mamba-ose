import numpy
from mamba.backend.zserver import raise_syntax, unary_op
from .common import roi_slice, norm_roi, norm_origin, roi2xywh, \
    auto_contours, img_phist, angular_vis, stage_wrap, AttiAdMixin

QUARTER_BINS = 90
RADIAL_BINS = 1000

def auto_roi(img, pad, threshold):
    rois = auto_contours(img, threshold)
    if not rois:
        return 0, img.shape[1], 0, img.shape[0]
    roi = rois[0]
    pad = min([pad, roi[0], roi[2],
        img.shape[1] - roi[1], img.shape[0] - roi[3]])
    return roi[0] - pad, roi[1] + pad, roi[2] - pad, roi[3] + pad

def img_eval(img, roi, origin):
    img = roi_slice(img, roi)
    origin = origin[0] - roi[0], origin[1] - roi[2]
    if not img.any():
        img = numpy.array([(1, 0), (0, 0)])
        roi = 0, 2, 0, 2
    angular = img_phist(img, origin, (0, 4 * QUARTER_BINS))
    angular[0][:] *= 4 * QUARTER_BINS / angular[0].sum()
    quad = angular[0].reshape((4, QUARTER_BINS)).sum(1)
    return (quad[0] + quad[3]) - (quad[1] + quad[2]), \
        (quad[0] + quad[1]) - (quad[2] + quad[3]), angular

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
    roi_threshold, roi_ratio, roi_steps = None, 0.95, 10

    def configure(self, ad, motors, ylimits, xlimits = None):
        assert int(ad.hdf1.ndimensions.get()) == len(motors) == 2
        if not xlimits:
            xlimits = [(m.low_limit_travel.get(), m.high_limit_travel.get())
                for m in motors]
            xlimits = [(0.9 * lo + 0.1 * hi, 0.1 * lo + 0.9 * hi)
                for lo, hi in xlimits]
        self.ad, self.motors = ad, motors
        self.devices = [self.ad] + self.motors
        self.optim = GradOptim(xlimits, ylimits)
        self.roi = self.origin = self.cache = None

    def move(self, xs):
        [s.wait() for s in [m.set(x) for m, x in zip(self.motors, xs)]]

    def refresh(self, acquire = True, origin = False):
        if acquire:
            self.cache = self.acquire()
        doc, img = self.cache
        doc = doc.copy(); doc["data"] = doc["data"].copy()
        if origin:
            if self.roi_threshold is None:
                flat = numpy.sort(img.flatten())
                threshold = flat[int(self.roi_ratio * len(flat))]
            else:
                threshold = self.roi_threshold
            self.roi = auto_roi\
                (img, min(img.shape) // self.roi_steps, threshold)
            self.origin = (self.roi[0] + self.roi[1]) // 2, \
                (self.roi[2] + self.roi[3]) // 2
        doc["data"]["eval"] = img_eval(img, self.roi, self.origin)
        angular = doc["data"]["eval"][-1]
        doc["data"]["eval"] = doc["data"]["eval"][:-1] + \
            (angular[0].std(), self.ad.cam.temperature_actual.get())
        radial = img_phist(img, self.origin, (RADIAL_BINS, 0))
        doc["data"]["hist"] = angular_vis\
            (img, self.origin, *angular) + (radial[1], radial[0])
        self.send_event(doc)
        return doc["data"]["eval"]

    def set_roi(self, roi):
        self.roi = norm_roi(roi, *self.cache[1].shape[::-1])

    def set_origin(self, origin):
        self.origin = norm_origin(origin, *self.cache[1].shape[::-1])

    @stage_wrap
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
    elif op == "roi_origin":
        return {"err": "", "ret": (roi2xywh(state.roi), state.origin)}
    raise_syntax(req)

def state_build(U, config, name):
    setattr(U, name, AttiXes(U.mzcb))

def saddon_xes(arg):
    name = arg or "atti_xes"
    return {"mzs": {name: mzs_xes},
        "state": lambda U, config: state_build(U, config, name)}

