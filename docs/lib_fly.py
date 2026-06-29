import numpy
from bluesky import plans, plan_stubs as bps, preprocessors as bpp
from butils.fly import fly_dgrid, sfly_grid
from butils.plans import \
    args_snake, make_sub_step, motors_get, norm_cache, norm_snake
from mamba.backend.planner import div_get
from mamba.backend.planner import PandaPlanner, BuboPlanner

def fly_test(pandas, dets, out_args, in_args,
    snake_axes = True, md = None, pos_cache = None, **kwargs):
    motors = motors_get(out_args) + motors_get(in_args)
    pos_cache = norm_cache(pos_cache)
    snake_axes = norm_snake(snake_axes, motors)
    gen = args_snake(in_args, snake_axes)
    def sub():
        yield from bps.trigger_and_read(list(dets) + motors)
        yield from fly_dgrid(pandas, dets, *gen(), **kwargs,
            snake_axes = snake_axes, pos_cache = pos_cache)
    args = out_args + in_args
    nums = [args[i * 4 + 3] for i in range(len(args) // 4)]
    _md = {"num_points": int(numpy.prod(nums)),
        "hints": {"progress": ["simple"] + nums[:-1] + [2]}}
    _md.update(md)
    return bpp.stage_run_wrapper(bpp.stub_wrapper(plans.grid_scan(
        dets, *out_args, snake_axes = snake_axes,
        per_step = make_sub_step(sub), pos_cache = pos_cache
    )), list(pandas) + [panda.ad for panda in pandas] +
        list(dets) + motors, md = _md)

def fly_stest(bubo, dets, out_args, in_args,
    snake_axes = True, md = None, pos_cache = None, **kwargs):
    motors = motors_get(out_args) + motors_get(in_args)
    pos_cache = norm_cache(pos_cache)
    snake_axes = norm_snake(snake_axes, motors)
    gen = args_snake(in_args, snake_axes)
    def sub():
        yield from bps.trigger_and_read(list(dets) + motors)
        yield from sfly_grid(bubo, dets, *gen(), **kwargs,
            snake_axes = snake_axes, pos_cache = pos_cache)
    args = out_args + in_args
    nums = [args[i * 4 + 3] for i in range(len(args) // 4)]
    _md = {"num_points": int(numpy.prod(nums)),
        "hints": {"progress": ["simple"] + nums[:-1] + [2]}}
    _md.update(md)
    return bpp.stage_run_wrapper(bpp.stub_wrapper(plans.grid_scan(
        dets, *out_args, snake_axes = snake_axes,
        per_step = make_sub_step(sub), pos_cache = pos_cache
    )), [bubo] + list(dets) + motors, md = _md)

class MyPandaPlanner(PandaPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plans["fly_test"] = self.plan_wrap("fly_test", fly_test)

    def args_conv(self, plan, args):
        if plan == "fly_test":
            args = [args[0]] + list(args[2])
        return args

    def check(self, plan, *args, **kwargs):
        return super().check(plan, *self.args_conv(plan, args), **kwargs)

    def callback(self, plan, *args, **kwargs):
        return super().callback(plan, *self.args_conv(plan, args), **kwargs)

class MyBuboPlanner(BuboPlanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plans["fly_stest"] = self.plan_wrap("fly_stest", fly_stest)

    def args_conv(self, plan, args):
        if plan == "fly_stest":
            args = [args[0]] + list(args[2])
        return args

    def callback(self, plan, *args, **kwargs):
        return super().callback(plan, *self.args_conv(plan, args), **kwargs)

