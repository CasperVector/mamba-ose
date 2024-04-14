import numpy
import os
import re
from PIL import Image
from scipy import optimize
from mamba.backend.zserver import raise_syntax, unary_op
from .common import roi_crop, norm_roi, norm_origin, roi2xywh, \
    random_simplex, bg_bad, auto_contours, img_phist, proj_peak, \
    angular_vis, ad_dim, stage_wrap, make_state, AttiOptim

RADIAL_BINS, ANGULAR_BINS = 1000, 360

def auto_bg(img, roi):
    crop = roi_crop(img, roi).reshape((-1,))
    return numpy.sort(crop)[len(crop) // 2]

def img_radial(img, origin, bg):
    radial = img_phist(img, origin, (RADIAL_BINS, 0))
    brad = numpy.maximum(radial[0], bg) - bg
    l = int(0.1 * len(brad))
    brad[:l] = 0.0; brad[-l:] = 0.0
    pos, roi = proj_peak(brad)
    return radial[0][roi[0] : roi[1]].mean(), radial, \
        radial[1][-1] / (RADIAL_BINS - 0.5) * (pos + 0.5)

def img_eval(img, roi, origin, bg):
    img = roi_crop(img, roi)
    origin = origin[0] - roi[0], origin[1] - roi[2]
    rev, radial, rad = img_radial(img, origin, bg)
    angular = img_phist(bg_bad(img.copy(), bg, 0), origin, (0, ANGULAR_BINS))
    mean = angular[0].sum() / ANGULAR_BINS
    if mean:
        angular[0][:] /= mean
    return rev, angular[0].std(), radial, angular

class AttiXes(AttiOptim):
    bg_threshold, atime_ratio = None, 1e3
    bad_threshold, origin_rad, origin_tol = 0, 1.0, 1.0
    init_rad, maxfev, xatol, fatol = 0.1, 25, 1e-2, (20, 5e-4)

    def configure(self, ad, motors):
        assert len(ad_dim(ad)) == 2
        super().configure([ad], motors)
        self.roi = self.origin = self.cache = None
        self.ad, self.img_name = ad, ad.name + "_image"

    def get_y(self, dets = None):
        self.cache = super().get_y(dets)
        return self.cache.copy()

    def save(self, output, img, radial):
        output = re.sub(r"\.(tiff?|txt)$", "", output)
        if img is None or radial is None:
            dname = os.path.dirname(output)
            assert os.access(dname, os.W_OK), \
                "path `%s' nonwritable or nonexistent" % dname
            for ext in [".tiff", ".txt"]:
                assert not os.access(output + ext, os.F_OK), \
                    "path `%s' already exists" % (output + ext)
            return
        Image.fromarray(img).save(output + ".tiff", "tiff")
        with open(output + ".txt", "w") as f:
            f.write((
                 "bad_threshold: %g\norigin: %g, %g\n" +
                 "roi: %d, %d, %d, %d\nradial:\n"
            ) % ((self.bad_threshold,) + self.origin + self.roi))
            numpy.savetxt(f, numpy.concatenate(
                (radial[1].reshape((-1, 1)), radial[0].reshape((-1, 1))), 1
            ), fmt = "%g")

    def proc(self, doc, output = "", mode = 0):
        img = bg_bad(doc["data"][self.img_name].copy(), 0, self.bad_threshold)
        doc["data"]["meta"] = {"x":
            [m.replace(".", "_") for m in self.motors]}
        ev = img_eval(img, self.roi, self.origin, self.bg_threshold)
        radial, angular = ev[-2:]
        doc["data"]["aeval"] = ev[:-2]
        doc["data"]["eval"] = [-ev[0], ev[1]][mode]
        doc["data"]["hist"] = (radial[1], radial[0]) + \
            angular_vis(img, self.origin, *angular)
        if output:
            self.save(output, doc["data"][self.img_name], radial)
        return doc["data"]["eval"]

    def reorigin(self, img):
        rad = [None]
        img, shape = roi_crop(img, self.roi), img.shape
        def func(origin):
            ev, radial, rad[0] = img_radial(img, origin, self.bg_threshold)
            self.send_event({"data": {
                "origin": (origin[0] + self.roi[0], origin[1] + self.roi[2]),
                "hist": radial[::-1] + (None, None)
            }})
            return -ev
        origin = self.origin[0] - self.roi[0], self.origin[1] - self.roi[2]
        origin = tuple(round(x) for x in optimize.minimize(
            func, origin, method = "nelder-mead", options = {
                "disp": True, "xatol": 1.0,
                "fatol": self.origin_tol * numpy.sqrt(self.bg_threshold),
                "initial_simplex": origin + self.origin_rad * random_simplex(2)
            }, callback = self.callback
        ).x)
        origin = origin[0] + self.roi[0], origin[1] + self.roi[2]
        rad = min([round(1.5 * rad[0]), origin[0], origin[1],
            shape[1] - origin[0], shape[0] - origin[1]])
        roi = origin[0] - rad, origin[0] + rad, origin[1] - rad, origin[1] + rad
        return origin, roi

    @stage_wrap
    def refresh(self, output = "", mode = "a"):
        if output:
            self.save(output, None, None)
        doc = self.get_y() if "a" in mode else self.cache.copy()
        doc["data"] = doc["data"].copy()
        img = doc["data"][self.img_name]
        if not self.origin:
            self.roi = 0, img.shape[1], 0, img.shape[0]
            self.origin = (self.roi[0] + self.roi[1]) // 2, \
                (self.roi[2] + self.roi[3]) // 2
        self.bg_threshold = auto_bg(img, self.roi)
        if "o" in mode:
            self.origin, self.roi = self.reorigin(img)
            self.bg_threshold = auto_bg(img, self.roi)
        self.proc(doc, output = output)
        self.send_event(doc)
        return doc["data"]["aeval"]

    def set_roi(self, roi):
        self.roi = norm_roi(roi, *self.cache["data"][self.img_name].shape[::-1])

    def set_origin(self, origin):
        self.origin = norm_origin(origin,
            *self.cache["data"][self.img_name].shape[::-1])

    @stage_wrap
    def tune(self, init_rad = None, mode = "radial"):
        if init_rad is None:
            init_rad = self.init_rad
        mode = ["radial", "angular"].index(mode)
        options = {
            "disp": True, "maxfev": self.maxfev,
            "xatol": self.xatol, "fatol": self.fatol[mode],
        }
        x0 = self.get_x()
        options["initial_simplex"] = x0 + init_rad * random_simplex(2)
        first = [True]
        def proc(doc):
            if first[0]:
                first[0], img = False, doc["data"][self.img_name]
                self.bg_threshold = auto_bg(img, self.roi)
            return self.proc(doc, mode = mode)
        optimize.minimize(
            self.wrap(list(self.dets), list(self.motors), proc), x0,
            method = "nelder-mead", options = options, callback = self.callback
        )

def mzs_xes(self, req):
    op, state = unary_op(req), self.get_state(req)
    if op == "roi_origin":
        return {"err": "", "ret": (roi2xywh(state.roi), state.origin)}
    elif op == "names":
        return {"err": "", "ret": {"atime_ratio": state.atime_ratio,
            "dets": list(state.dets), "motors": list(state.motors)}}
    raise_syntax(req)

def saddon_xes(arg):
    name = arg or "atti_xes"
    return {"mzs": {name: mzs_xes}, "state": make_state(name, AttiXes)}

