from scipy import optimize
from mamba.attitude.common import stage_wrap, make_saddon, AttiOptim

class AttiCapi(AttiOptim):
    def proc(self, doc, output, motors):
        doc["data"]["meta"] = {"x": motors, "y": output}
        doc["data"]["eval"] = doc["data"][output + "_image"]
        return doc["data"]["eval"]

    def tune_base(self, det, motors, *, maxfev):
        return optimize.minimize(
            self.wrap([det], motors, lambda doc: self.proc(
                doc, det.replace(".", "_"),
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
            self.tune_base("D.rosen1", ["M.m1", "M.m2"], maxfev = 150)
        elif area == "3":
            self.tune_base("D.rosen1", ["M.m3"], maxfev = 75)
        elif area == "4":
            self.tune_base("D.rosen2", ["M.m4"], maxfev = 75)
        else:
            raise RuntimeError("unknown area `%s'" % area)

    @stage_wrap
    def tune(self, *args, **kwargs):
        self.tune_area(*args, **kwargs)

saddon_capi = make_saddon("atti_capi", AttiCapi, ["D_rosen1", "D_rosen2"])

