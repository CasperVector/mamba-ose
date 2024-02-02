import numpy
from scipy import optimize
from mamba.backend.zserver import raise_syntax, unary_op
from .common import roi_crop, norm_roi, norm_origin, roi2xywh, \
    random_simplex, bg_bad, auto_contours, img_phist, proj_peak, \
    angular_vis, ad_dim, stage_wrap, make_state, AttiOptim

RADIAL_BINS, ANGULAR_BINS = 1000, 360

def auto_roi(img, pad, threshold):
    rois = auto_contours(img, threshold)
    if not rois:
        return 0, img.shape[1], 0, img.shape[0]
    roi = rois[0]
    pad = min([pad, roi[0], roi[2],
        img.shape[1] - roi[1], img.shape[0] - roi[3]])
    return roi[0] - pad, roi[1] + pad, roi[2] - pad, roi[3] + pad

def img_eval(img, roi, origin, bg):
    img = roi_crop(img, roi)
    origin = origin[0] - roi[0], origin[1] - roi[2]
    if not img.any():
        img = numpy.array([(1, 0), (0, 0)])
        roi = 0, 2, 0, 2
    radial = img_phist(img, origin, (RADIAL_BINS, 0))
    brad = numpy.maximum(radial[0], bg) - bg
    l = int(0.1 * len(brad))
    brad[:l] = 0.0; brad[-l:] = 0.0
    pos, roi = proj_peak(brad)
    angular = img_phist(bg_bad(img.copy(), bg, 0), origin, (0, ANGULAR_BINS))
    angular[0][:] *= ANGULAR_BINS / angular[0].sum()
    return radial[0][roi[0] : roi[1]].mean(), angular[0].std(), radial, angular

class AttiXes(AttiOptim):
    bg_threshold, bad_threshold, roi_steps = 1000, 0, 10
    init_rad, maxfev, xatol, fatol = 0.1, 25, 1e-2, (20, 5e-4)

    def configure(self, ad, motors):
        assert len(ad_dim(ad)) == 2
        super().configure([ad], motors)
        self.roi = self.origin = self.cache = None
        self.ad, self.ad_name = ad, ad.name + "_image"

    def get_y(self, dets = None):
        self.cache = super().get_y(dets)
        return self.cache.copy()

    def proc(self, doc, mode = 0):
        img = bg_bad(doc["data"][self.ad_name], 0, self.bad_threshold)
        doc["data"]["meta"] = {"x":
            [m.replace(".", "_") for m in self.motors]}
        ev = img_eval(img, self.roi, self.origin, self.bg_threshold)
        radial, angular = ev[-2:]
        doc["data"]["aeval"] = ev[:-2] + (self.ad.cam.temperature_actual.get(),)
        doc["data"]["eval"] = [-ev[0], ev[1]][mode]
        doc["data"]["hist"] = (radial[1], radial[0]) + \
            angular_vis(img, self.origin, *angular)
        return doc["data"]["eval"]

    @stage_wrap
    def refresh(self, acquire = True, origin = False):
        doc = self.get_y() if acquire else self.cache.copy()
        doc["data"] = doc["data"].copy()
        if origin:
            img = doc["data"][self.ad_name]
            self.roi = auto_roi\
                (img, min(img.shape) // self.roi_steps, self.bg_threshold)
            self.origin = (self.roi[0] + self.roi[1]) // 2, \
                (self.roi[2] + self.roi[3]) // 2
        self.proc(doc)
        self.send_event(doc)
        return doc["data"]["aeval"]

    def set_roi(self, roi):
        self.roi = norm_roi(roi, *self.cache["data"][self.ad_name].shape[::-1])

    def set_origin(self, origin):
        self.origin = norm_origin(origin,
            *self.cache["data"][self.ad_name].shape[::-1])

    @stage_wrap
    def auto_tune(self, mode = "radial"):
        mode = ["radial", "angular"].index(mode)
        options = {
            "disp": True, "maxfev": self.maxfev,
            "xatol": self.xatol, "fatol": self.fatol[mode],
        }
        x0 = self.get_x()
        options["initial_simplex"] = x0 + self.init_rad * random_simplex(2)
        optimize.minimize(self.wrap(
            list(self.dets), list(self.motors),
            lambda doc: self.proc(doc, mode)
        ), x0, method = "nelder-mead", options = options)

def mzs_xes(self, req):
    op, state = unary_op(req), self.get_state(req)
    if op == "roi_origin":
        return {"err": "", "ret": (roi2xywh(state.roi), state.origin)}
    elif op == "names":
        return {"err": "", "ret":
            [[d.replace(".", "_") + "_image" for d in state.dets],
            [m.replace(".", "_") for m in state.motors]]
        }
    raise_syntax(req)

def saddon_xes(arg):
    name = arg or "atti_xes"
    return {"mzs": {name: mzs_xes}, "state": make_state(name, AttiXes)}

