import numpy
from mamba.backend.zserver import raise_syntax, unary_op
from .common import roi_crop, norm_roi, roi2xywh, \
    bg_bad, auto_contours, img_peak, max_parascan, perm_diffmax, \
    ad_dim, stage_wrap, make_state, AttiOptim

def focus_eval(info, threshold):
    total, area = info[2]
    return total / area if total >= threshold else 0.0

def auto_rois(img, rad, threshold):
    ret = sorted(((x0 + x1) // 2, (y0 + y1) // 2)
        for x0, x1, y0, y1 in auto_contours(img, threshold))
    return [(x - rad, x + rad, y - rad, y + rad) for x, y in ret]

class AttiRaman(AttiOptim):
    bg_threshold, bad_threshold, eval_threshold = 0, 0, 512
    roi_steps, roi_threshold, perm_steps, perm_ratio = 10, 8, (48, 32), 5
    focus_groups, focus_steps, focus_ratio = 3, (25, 100), (0.5, 0.8)

    def focus_eval(self, img):
        return focus_eval(img_peak(img), self.eval_threshold)

    def configure(self, ad, motors, bounds = None):
        self.dim = ad_dim(ad)
        assert len(self.dim) == 2
        if ad.vname() in self.ad_rois:
            self.dim = roi2xywh(self.ad_rois[ad.vname()])[-2:]
        if bounds:
            assert len(bounds) == len(motors)
        else:
            bounds = [(m.low_limit_travel.get(), m.high_limit_travel.get())
                for m in motors]
            bounds = [(0.9 * lo + 0.1 * hi, 0.1 * lo + 0.9 * hi)
                for lo, hi in bounds]
        super().configure([ad], motors)
        self.ad, self.ad_name = ad, ad.name + "_image"
        self.bounds, self.rois = numpy.array(bounds).reshape((-1, 3, 2)), None
        self.groups = [list(range(i, len(self.bounds), self.focus_groups))
            for i in range(self.focus_groups)]

    def set_rois(self, rois, ids = []):
        if not self.rois:
            self.rois = [(0, 1, 0, 1)] * len(self.bounds)
        if not ids:
            ids = range(len(self.bounds))
        for i, roi in zip(ids, rois):
            self.rois[i] = norm_roi(roi, *self.dim)

    @stage_wrap
    def refresh(self, roi = False):
        doc = self.get_y()
        self.send_event(doc)
        if not roi:
            return
        rois = auto_rois(doc["data"][self.ad_name],
            min(self.dim) // self.roi_steps, self.roi_threshold)
        self.set_rois(rois)
        return max(len(self.bounds) - len(rois), 0)

    def perm_rois(self, perm):
        self.rois = [self.rois[i] for i in perm]

    def func_perm(self, x, i, y0):
        if i >= 0:
            self.put_x(x, [3 * i + 1, 3 * i + 2])
        doc = self.get_y()
        img = bg_bad(doc["data"][self.ad_name].copy(),
            self.bg_threshold, self.bad_threshold)
        y = numpy.array([img_peak(roi_crop(img, roi))[0] for roi in self.rois])
        if i < 0:
            y0 = y
        doc["data"]["eval"] = numpy.sqrt((y - y0) ** 2).sum(1)
        self.send_event(doc)
        return y, doc["data"]["eval"]

    @stage_wrap
    def auto_perm(self):
        assert self.rois, "need set_rois()"
        bounds = self.bounds[:, 1 : 3, :].copy()
        for i in set(range(len(bounds))) - set(sum(self.groups, [])):
            bounds[i] = numpy.nan
        err, perm = perm_diffmax(
            self.func_perm, self.get_x().reshape((-1, 3))[:, 1 : 3],
            bounds = bounds, steps = self.perm_steps[0],
            threshold = (self.perm_ratio, min(self.dim) / self.perm_steps[1])
        )
        self.perm_rois(perm)
        return err, perm

    def proc_focus(self, doc, group):
        img = bg_bad(doc["data"][self.ad_name].copy(),
            self.bg_threshold, self.bad_threshold)
        doc["data"]["eval"] = \
            [self.focus_eval(roi_crop(img, roi)) for roi in self.rois]
        return [doc["data"]["eval"][i] for i in group]

    def focus(self, group):
        motors = list(self.motors)
        return max_parascan(
            self.wrap(
                [self.ad.vname()], [motors[3 * i] for i in group],
                lambda doc: self.proc_focus(doc, group)
            ), bounds = self.bounds[group, 0, :],
            steps = self.focus_steps, threshold = self.focus_ratio
        )

    @stage_wrap
    def auto_focus(self):
        assert self.rois, "need set_rois()"
        err, ret = [], []
        for group in self.groups:
            if ret is not None:
                ret = self.focus(group)
            err += group if ret is None else [group[j] for j in ret]
        return sorted(err)

def mzs_raman(self, req):
    op, state = unary_op(req), self.get_state(req)
    if op == "rois":
        return {"err": "", "ret": [roi2xywh(roi) for roi in state.rois]}
    elif op == "names":
        return {"err": "", "ret":
            [[d.replace(".", "_") + "_image" for d in state.dets],
            [m.replace(".", "_") for m in state.motors], state.dim]
        }
    raise_syntax(req)

def saddon_raman(arg):
    name = arg or "atti_raman"
    return {"mzs": {name: mzs_raman}, "state": make_state(name, AttiRaman)}

