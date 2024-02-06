import h5py
import numpy
import os
from butils.ophyd import para_move
from ..backend.zserver import raise_syntax, unary_op
try:
    import cv2
except ImportError:
    pass

def roi_crop(img, roi):
    return img[roi[2] : roi[3], roi[0] : roi[1]]

def norm_roi(roi, w, h):
    x0, x1, y0, y1 = map(int, numpy.clip(roi, 0, (w, w, h, h)))
    return (x0, x1, y0, y1) if x0 < x1 and y0 < y1 else (0, w, 0, h)

def norm_origin(origin, w, h):
    return tuple(map(int, numpy.clip(origin, 0, (w, h))))

def roi2xywh(roi):
    x0, x1, y0, y1 = roi
    return x0, y0, x1 - x0, y1 - y0

def xywh2roi(xywh):
    x, y, w, h = xywh
    return x, x + w, y, y + h

def norm_xywh(xywh, w, h):
    return roi2xywh(norm_roi(xywh2roi(xywh), w, h))

def xywhs2rois(xywhs):
    return [xywh2roi(xywh) for xywh in xywhs]

def random_simplex(dim):
    return numpy.concatenate((
        numpy.zeros((dim,)).reshape((1, -1)),
        numpy.diag(numpy.random.choice([1, -1], size = (dim,)))
    ))

def bg_bad(img, bg_threshold, bad_threshold):
    if bad_threshold:
        img[img > bad_threshold] = 0
    if bg_threshold:
        img[img < bg_threshold] = bg_threshold
        img -= bg_threshold
    return img

def auto_contours(img, threshold):
    img = cv2.GaussianBlur(img.astype("float64"), (0, 0), cv2.BORDER_DEFAULT)
    mask = (img >= threshold).astype("uint8")
    ret = [xywh2roi(cv2.boundingRect(contour)) for contour in
        cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]]
    ret = sorted((-roi_crop(img, roi).sum(), roi) for roi in ret)
    return [roi for total, roi in ret]

def proj_peak(proj):
    peak = numpy.mean(proj[proj >= 0.95 * proj.max()]) / 0.98
    pos = int(numpy.mean((proj >= 0.95 * peak).nonzero()))
    roi = (proj[:pos] < peak / 2).astype(int).sum(), \
        len(proj) - (proj[pos:] < peak / 2).astype(int).sum()
    return pos, roi

def img_peak(img):
    pos, roi = zip(*[proj_peak(img.sum(i)) for i in [0, 1]])
    roi = roi[0] + roi[1]
    return pos, roi, (roi_crop(img, roi).sum(), \
        (roi[1] - roi[0]) * (roi[3] - roi[2]))

def img_polar(shape, origin):
    h, w = shape
    coords = numpy.full((h, w), numpy.arange(w) - origin[0]) * (1 + 0j)
    coords += numpy.full((w, h), origin[1] - numpy.arange(h)).T * (0 + 1j)
    rads, thetas = numpy.abs(coords), numpy.angle(coords)
    thetas[thetas < 0] += 2 * numpy.pi
    return rads, thetas

def img_phist(img, origin, nbins):
    ret = ()
    if any(nbins):
        img = img.astype(float)
    rads, thetas = img_polar(img.shape, origin)
    if nbins[0]:
        bins = numpy.arange(nbins[0] + 1) / nbins[0] * rads.max()
        hist = 1.0 * numpy.histogram(rads, bins)[0]
        hist[hist.nonzero()] = 1.0 / hist[hist.nonzero()]
        hist *= numpy.histogram(rads, bins, weights = img)[0]
        ret += hist, bins[:-1] + 0.5 * rads.max() / nbins[0]
    if nbins[1]:
        bins = numpy.arange(nbins[1] + 1) / nbins[1] * (2 * numpy.pi)
        ret += numpy.histogram(thetas, bins, weights = img)[0], \
            bins[:-1] + numpy.pi / nbins[1]
    if not ret:
        ret = rads, thetas
    return ret

def angular_vis(img, origin, hist, bins):
    hist = (hist - hist.mean()) / hist.std() * 0.125 + 0.5
    if numpy.isfinite(hist).all():
        hist[hist < 0.125] = 0.125
        hist[hist > 0.875] = 0.875
    else:
        hist[:] = 0.5
    hist, bins = numpy.append(hist, hist[0]), numpy.append(bins, bins[0])
    angular = hist * numpy.exp(bins * (0 + 1j)) * min(origin[0], origin[1],
        img.shape[1] - origin[0], img.shape[0] - origin[1])
    return origin[0] + numpy.real(angular), origin[1] - numpy.imag(angular)

def cb_stop(cb, *args, **kwargs):
    if not cb:
        return False
    try:
        cb(*args, **kwargs)
        return False
    except StopIteration:
        return True

def max_parascan(func, *, callback = None, bounds, steps, threshold):
    bounds, n = numpy.array(bounds), len(bounds)
    x, d = bounds[:,0], (bounds[:,1] - bounds[:,0]) / steps[0]
    ys = numpy.zeros((steps[0] + 1, bounds.shape[0]))
    for i in range(steps[0] + 1):
        ys[i] = func(x)
        if cb_stop(callback, ys[i]):
            return None
        x = x + d
    err, maxs = [], ys.max(0)
    ys = ys >= maxs * threshold[0]
    x = numpy.array([ys[:,i].nonzero()[0][-1] for i in range(n)])
    x, d = bounds[:,0] + d * x, (bounds[:,0] - bounds[:,1]) / steps[1]
    best = [[None, None] for i in range(n)]

    while d.sum():
        y = func(x)
        if cb_stop(callback, y):
            return None
        for i in range(n):
            if not d[i]:
                continue
            elif best[i][0] is None and y[i] >= maxs[i] * threshold[1]:
                best[i][0] = x[i]
            elif best[i][0] is not None and best[i][1] is None \
                and y[i] < maxs[i] * threshold[1]:
                best[i][1], d[i] = x[i] - d[i], 0.0
            elif (x[i] + d[i] - bounds[i, 0]) * d[i] > 0:
                if best[i][0] is not None:
                    best[i][1] = bounds[i, 0]
                d[i] = 0.0
        x += d

    for i in range(n):
        if best[i][0] is not None and best[i][1] is not None:
            x[i] = (best[i][0] + best[i][1]) / 2
        else:
            err.append(i)
    if cb_stop(callback, func(x)):
        return None
    return err

def find_dmax(diff, ratio, threshold = 0):
    dsort = sorted(diff, key = lambda e: -e)
    dmax, dsecond = dsort[0], (dsort[1] if len(dsort) > 1 else 0.0)
    return list(diff).index(dmax) if dmax > dsecond * ratio \
        and dmax > threshold else None

def perm_diffmax(func, x0, *, callback = None, bounds, steps, threshold):
    x0, bounds, n = numpy.array(x0), numpy.array(bounds), len(bounds)
    err, perm, (y0, diff) = [], [None] * n, func(None, -1, None)
    d = numpy.array([[(hi - lo) / steps * (-1 if x - lo > hi - x else 1)
        for x, (lo, hi) in zip(x0[i], bounds[i])] for i in range(n)])
    def mk_return():
        for i in range(n):
            if i not in perm:
                j = perm.index(None)
                perm[j] = i
                if numpy.isfinite(d[j]).all():
                    err.append(i)
        return err, perm
    if cb_stop(callback, y0):
        return mk_return()

    for i in range(n):
        if not numpy.isfinite(d[i]).any():
            continue
        def mk_break(j):
            y, diff = func(x0[i], i, y0)
            y0[:], ret = y, True
            if cb_stop(callback, y):
                j, ret = None, False
            if j not in perm:
                perm[i] = j
            return ret

        x, j = x0[i], None
        while True:
            x = x + d[i]
            if j is not None or (x < bounds[i,:,0]).any() \
                or (x > bounds[i,:,1]).any():
                if mk_break(j): break
                else: return mk_return()
            y, diff = func(x, i, y0)
            if cb_stop(callback, y):
                return mk_return()
            j = find_dmax(diff, threshold[0], threshold[1])
    return mk_return()

def ad_dim(ad):
    if hasattr(ad, "hdf1"):
        return tuple(reversed(ad.hdf1.array_size.get()))\
            [:int(ad.hdf1.ndimensions.get())]
    img = ad.image.get()
    if hasattr(img, "shape"):
        return img.shape[::-1]
    return ()

def stage_wrap(f):
    def g(obj, *args, **kwargs):
        obj.stage()
        try:
            return f(obj, *args, **kwargs)
        finally:
            obj.unstage()
    return g

class AttiOptim(object):
    def __init__(self, mzcb):
        self.ad_rois = {}
        self.motors = self.dets = self.ads = None
        self.send_event = lambda doc: mzcb("event", doc)
        self.stopped = False

    def configure(self, dets, motors):
        self.dets = {d.vname(): d for d in dets}
        self.motors = {m.vname(): m for m in motors}
        self.ads = {d.vname(): None for d in dets if hasattr(d, "hdf1")}

    def stage(self):
        self.stopped = False
        for d in self.dets.values():
            d.stage()
        for a in self.ads:
            self.ads[a] = h5py.File(
                self.dets[a].hdf1.full_file_name.get(), "r", swmr = True
            )["entry/data/data"]

    def unstage(self, clean = True):
        for a, d in reversed(list(self.ads.items())):
            f = d.file.filename
            d.file.close()
            self.ads[a] = None
            if clean:
                os.remove(f)
        for d in reversed(list(self.dets.values())):
            d.unstage()

    def stop(self):
        self.stopped = True
        for m in self.motors.values():
            m.stop()

    def callback(self, *args, **kwargs):
        if self.stopped:
            raise StopIteration()

    def get_x(self, motors = None):
        motors = motors or list(self.motors)
        return numpy.array([self.motors[m].position for m in motors])

    def put_x(self, x, motors = None):
        motors = motors or list(self.motors)
        if not all(isinstance(m, str) for m in motors):
            names = list(self.motors)
            motors = [names[i] for i in motors]
        para_move(dict(zip([self.motors[m] for m in motors], x)))

    def get_y(self, dets = None):
        data = {}
        dets = dets or list(self.dets)
        [s.wait() for s in [self.dets[d].trigger() for d in dets]]
        [d.refresh() for a, d in self.ads.items() if a in dets]
        [data.update(m.read()) for m in self.motors.values()]
        [data.update(self.dets[d].read()) for d in dets]
        data, timestamps = [{k: data[k][field] for k in data}
            for field in ["value", "timestamp"]]
        data.update([
            (a.replace(".", "_") + "_image", numpy.array(d[-1]))
            for a, d in self.ads.items() if a in dets
        ])
        for a, r in self.ad_rois.items():
            if a in dets:
                a = a.replace(".", "_") + "_image"
                data[a] = roi_crop(data[a], r)
        return {"data": data, "timestamps": timestamps}

    def wrap(self, dets, motors, proc):
        def f(x):
            self.put_x(x, motors)
            doc = self.get_y(dets)
            y = proc(doc)
            self.send_event(doc)
            return y
        return f

def make_mzs(outputs = None):
    def mzs(self, req):
        op, state = unary_op(req), self.get_state(req)
        if op == "names":
            ret = {} if outputs is None else {"outputs": outputs}
            ret.update({"dets": list(state.dets), "motors": list(state.motors)})
            return {"err": "", "ret": ret}
        raise_syntax(req)
    return mzs

def make_state(name, cls):
    return lambda U, config: setattr(U, name, cls(U.mzcb))

def make_saddon(atti, cls, outputs = None):
    def saddon(arg):
        name = arg or atti
        return {"mzs": {name: make_mzs(outputs)},
            "state": make_state(name, cls)}
    return saddon

