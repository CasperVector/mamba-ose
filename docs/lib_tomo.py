import numpy
from scipy import optimize
from bluesky import plans
from butils.data import ProcessorCallback
from mamba.attitude.common import \
    img_peak, make_saddon, random_simplex, AttiOptim
from mamba.backend.planner import MambaPlanner

class AttiTomo(AttiOptim):
    def configure(self, dets, pitch_rolls, yaws, P):
        super().configure(dets, pitch_rolls)
        self.yaws = {m.vname(): m for m in yaws}
        self.P, self.pitch_rolls = P, self.motors

    def preproc_tomo(self, doc, ad):
        data = doc["data"]
        info = img_peak(data[ad + "_image"])
        assert info[2][0] >= 5000 and info[2][1] <= 100
        data[ad + "_spot_x"], data[ad + "_spot_y"] = info[0]
        data[ad + "_spot_total"], data[ad + "_spot_area"] = info[2]

    def postproc_tomo(self, xs, ys, atti_out):
        i90, i270 = numpy.argmax(xs), numpy.argmin(xs)
        assert abs(abs(i270 - i90) / len(xs) - 0.5) < 0.1
        i180, i0 = (i90 + i270) // 2, (i90 + i270 + len(xs)) // 2 % len(xs)
        if i90 > i270:
            i0, i180 = i180, i0
        atti_out[:] = [ys[i180] - ys[i0], ys[i270] - ys[i90],
            xs[i180] - xs[i0], xs[i270] - xs[i90]]

    def get_y(self, ad, pitch_roll, yaw):
        data, atti_out, ad_name = {}, [], ad.replace(".", "_")
        [data.update(m.read()) for m in self.pitch_rolls.values()]
        data, timestamps = [{k: data[k][field] for k in data}
            for field in ["value", "timestamp"]]
        data["meta"] = {"x": [m.replace(".", "_") for m in pitch_roll], "y":
            [ad_name + s for s in ["_shift", "_shift_pitch", "_shift_roll"]]}
        self.P.grid_scan([self.dets[ad]], self.yaws[yaw],
            0.0, 270.0, 4, atti_out = atti_out)
        data["aeval"] = atti_out
        data["eval"] = [x ** 2 for x in atti_out[:2]]
        data["eval"] = [sum(data["eval"])] + data["eval"]
        return {"data": data, "timestamps": timestamps}

    def wrap(self, ad, pitch_roll, yaw):
        def f(x, first = False):
            self.put_x(x, pitch_roll)
            doc = self.get_y(ad, pitch_roll, yaw)
            self.send_event(doc)
            return doc["data"]["aeval"] if first else doc["data"]["eval"][0]
        return f

    def tune_base(self, dets, motors, *, maxfev, init_rad):
        (ad,), pitch_roll, (yaw,) = dets, motors[:2], motors[2:]
        f = self.wrap(ad, pitch_roll, yaw)
        x0 = self.get_x(pitch_roll)
        y0 = f(x0, True)
        x0 = x0 + numpy.degrees([numpy.sign(y0[0]) * numpy.arcsin(
            ((y0[0] ** 2 + y0[2] ** 2) / (y0[1] ** 2 + y0[3] ** 2)) ** 0.5
        ), numpy.arctan(y0[1] / y0[3])])
        return optimize.minimize(f, x0, method = "nelder-mead", options = {
            "disp": True, "maxfev": maxfev, "xatol": 0.05, "fatol": 1.0,
            "initial_simplex": x0 + init_rad * random_simplex(2)
        })

    def tune(self, init_rad = 0.5):
        self.tune_base(["D.ad"], ["M.pitch", "M.roll", "M.yaw"],
            maxfev = 50, init_rad = init_rad)

class MyMambaPlanner(MambaPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for plan in ["grid_scan", "list_grid_scan"]:
            self.plans[plan] = self.atti_deco(getattr(plans, plan))
        #import matplotlib.pyplot; matplotlib.pyplot.ion()
        #from butils.data import MyLiveImage
        #self.liveimg = MyLiveImage("D_ad_image")

    def atti_deco(self, inner):
        def plan(*args, **kwargs):
            kwargs.pop("atti_out", None)
            return inner(*args, **kwargs)
        return plan

    def callback(self, plan, *args, **kwargs):
        if "atti_out" not in kwargs:
            return super().callback(plan, *args, **kwargs)
        #if kwargs["atti_out"] is None:
        #    return [self.liveimg] + super().callback(plan, *args, **kwargs)
        ad, = args[0]
        preproc = lambda doc: self.U.atti_tomo.preproc_tomo(doc, ad.name)
        postproc = lambda xs, ys: \
            self.U.atti_tomo.postproc_tomo(xs, ys, kwargs["atti_out"])
        return [ProcessorCallback(
            [ad.name + "_spot_" + s for s in ["x", "y"]], postproc, preproc
        ), self.U.mzcb] #self.liveimg

saddon_tomo = make_saddon("atti_tomo", AttiTomo,
    ["D_ad_shift", "D_ad_shift_pitch", "D_ad_shift_roll"])

