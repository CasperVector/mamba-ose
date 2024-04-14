import collections
from ophyd.ophydobj import OphydObject
from bluesky import plan_stubs as bps, preprocessors as bpp

def plan_fmt(obj):
    if isinstance(obj, OphydObject):
        return obj.vname()
    elif isinstance(obj, list):
        return [plan_fmt(x) for x in obj]
    elif isinstance(obj, tuple):
        return tuple(plan_fmt(x) for x in obj)
    elif isinstance(obj, set):
        return set(plan_fmt(x) for x in obj)
    elif isinstance(obj, dict):
        return dict((plan_fmt(k), plan_fmt(v)) for k, v in obj.items())
    else:
        return obj

def motors_get(args, use_list = False):
    return list(args[::2] if use_list else args[::4])

def norm_cache(pos_cache):
    return collections.defaultdict(lambda: None) \
        if pos_cache is None else pos_cache

# Consistent with bluesky.plan_patterns.outer_list_product.
def norm_snake(snake_axes, motors):
    if isinstance(snake_axes, collections.abc.Iterable):
        return snake_axes
    elif snake_axes:
        return motors
    else:
        return []

def args_snake(args, snake_axes, use_list = False):
    args, unit = list(args), 2 if use_list else 4
    snaking = args[0 :: unit], args[unit - 1 :: unit]
    if use_list:
        snaking = snaking[0], [len(l) for l in snaking[1]]
    snaking = [ax in snake_axes and num % 2 for ax, num in
        zip(snaking[0], [1] + snaking[1][:-1])]
    def args_gen():
        cur = args.copy()
        for i in range(len(args) // unit):
            if not snaking[i]:
                pass
            elif use_list:
                args[i * 2 + 1] = args[i * 2 + 1][::-1]
            else:
                args[i * 2 + 1], args[i * 2 + 2] = \
                    args[i * 2 + 2], args[i * 2 + 1]
        return cur
    return args_gen

def make_sub_step(sub):
    def one_sub_step(detectors, step, pos_cache,
        take_reading = bps.trigger_and_read):
        if pos_cache["super_step"] is None:
            pos_cache["super_step"] = {}
        pos_cache["super_step"].update(step)
        yield from bpp.stub_wrapper(sub())
    return one_sub_step

