from scipy import optimize
from mamba.attitude.common import stage_wrap, make_saddon, AttiOptim
from mamba.backend.planner import AttiPlanner

class AttiCapi(AttiOptim):
    def proc(self, doc, outputs, motors):
        doc["data"]["meta"] = {"x": motors, "y": outputs}
        doc["data"]["eval"] = [doc["data"][y + "_image"] for y in outputs]
        return doc["data"]["eval"][0]

    def tune_base(self, dets, motors, *, maxfev):
        return optimize.minimize(
            self.wrap(dets, motors, lambda doc: self.proc(
                doc, [d.replace(".", "_") for d in dets],
                [m.replace(".", "_") for m in motors]
            )), self.get_x(motors), callback = self.callback,
            method = "nelder-mead", options =
                {"disp": True, "maxfev": maxfev, "xatol": 1e-3, "fatol": 2e-2}
        )

    def tune_area(self, area = None):
        if area is None:
            self.tune_area("12")
            self.tune_area("3")
            self.tune_area("4")
        elif area == "12":
            self.tune_base(["D.rosen1", "D.rosen2"],
                ["M.m1", "M.m2"], maxfev = 150)
        elif area == "3":
            self.tune_base(["D.rosen1", "D.rosen2"], ["M.m3"], maxfev = 75)
        elif area == "4":
            self.tune_base(["D.rosen2", "D.rosen1"], ["M.m4"], maxfev = 75)
        else:
            raise RuntimeError("unknown area `%s'" % area)

    @stage_wrap
    def tune(self, *args, **kwargs):
        self.tune_area(*args, **kwargs)

class CapiPlanner(AttiPlanner):
    def callback(self, plan, *args, **kwargs):
        assert plan == "atti_scan"
        (det,), motors = args[0], args[1 : -1 : 3]
        proc = lambda name, doc: name == "event" and \
            self.atti.proc(doc, det.name, [m.name for m in motors])
        return [proc, self.U.mzcb]

saddon_capi = make_saddon("atti_capi", AttiCapi, ["D_rosen1", "D_rosen2"])

