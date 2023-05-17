from bluesky import plans
from .progress import ProgressReporter, progressBars

class BasePlanner(object):
    plans, U = [], None

    def __init__(self):
        self.plans = {k: getattr(plans, k) for k in self.plans}

    def check(self, plan, *args, **kwargs):
        pass

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb]

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        return self.U.RE(self.plans[plan](*args, **kwargs), cb)

class ChildPlanner(BasePlanner):
    parent = None

class ParentPlanner(BasePlanner):
    def __init__(self, U):
        super().__init__()
        self.U, self.origins = U, [self]

    def extend(self, child):
        self.origins.append(child)
        child.U, child.parent = self.U, self

    def make_plans(self):
        ret = type("MambaPlans", (object,), {})()
        for obj in self.origins:
            for plan in obj.plans:
                setattr(ret, plan, (lambda run, plan:
                    lambda *args, **kwargs: run(plan, *args, **kwargs)
                )(obj.run, plan))
        return ret

class MambaPlanner(ParentPlanner):
    plans = ["grid_scan", "scan", "count"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plans["grid_scan"] = lambda *args, snake_axes = True, **kwargs: \
            plans.grid_scan(*args, snake_axes = snake_axes, **kwargs)
        self.progress = ProgressReporter(progressBars, self.U.mzs.notify)

    def callback(self, plan, *args, **kwargs):
        return [self.U.mzcb, self.progress]

    def run(self, plan, *args, **kwargs):
        self.check(plan, *args, **kwargs)
        cb = self.callback(plan, *args, **kwargs)
        return self.U.RE(self.plans[plan](*args, **kwargs),
            cb, md = self.U.mdg.read_advance())

