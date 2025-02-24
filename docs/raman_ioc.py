#!/usr/bin/python3
#
# $ (cd /opt/epics/motorSimIOC/iocBoot/iocMotorSim && \
#       ../../bin/linux-x86_64/motorSim ./st.cmd)
# $ /path/to/raman_ioc.py --list-pvs --prefix B5: \
#       --motor IOC: --hub B5: --mods 1

import re
from caproto.server import template_arg_parser
from queue_iocs.qioc_seq import QMotorHubIOCBase

class MhubB5IOCBase(QMotorHubIOCBase):
    def __init__(self, motor_pvs, hub_pvs, nmod, **kwargs):
        hubs, minfo = {}, self._motors
        i, j = 0, len(hub_pvs) // nmod
        super().__init__(motor_pvs, **kwargs)
        for motor, num in minfo:
            for sub in range(num):
                hubs[(motor, sub)], = self._ectx.get_pvs(hub_pvs[i])
                i += 1
        self._hubs = hubs

    def on_choose(self, motor, sub):
        print(motor, sub)

def make_minfo(mods):
    bases = ["vb", "vu", "vd", "hb", "hl", "hr"]
    groups = [([("%%s_foc%s" % c, "mhaydon%%d%s" % c) for c in "abcde"], 3),
        ([("%s_th", "mopto%d1"), ("%s_chi", "mopto%d2")], 15)]
    minfo = [(m % bases[i], nax) for i in mods
        for group, nax in groups for m, _ in group]
    motor_pvs = ["m%d" % (i + 1) for i in
        range(len(mods) * sum(len(group) for group, nax in groups))]
    hub_pvs = [
        ("hv%d:%s_%d" % (i + 1, m[3:], j + 1) if m[3:].startswith("foc")
        else "hv%d:%s_%s%d" % (i + 1, m[3:], "abcde"[j // 3], j % 3 + 1))
        for i in mods for group, nax in groups
        for m, _ in group for j in range(nax)
    ]
    def trans(name):
        match = re.match("([^_]+)_([^_]+)_sub([0-9]+)$", name)
        if not match:
            return name
        base, motor, sub = match.groups()
        sub = int(sub)
        return "%s_%s%d_%s" % ((base, "abcde"[sub // 3], sub % 3 + 1, motor)
            if motor in ["th", "chi"] else
            (base, motor[-1], sub + 1, motor[:-1]))
    return minfo, trans, motor_pvs, hub_pvs

def make_mhubb5(**options):
    mods = [int(x) - 1 for x in sorted(set(options["macros"]["mods"]))]
    minfo, trans, motor_pvs, hub_pvs = make_minfo(mods)
    class MhubB5IOC(MhubB5IOCBase.make_ioc(minfo, trans)):
        _choose_delay1, _choose_delay2 = 0.1, 0.5
    return MhubB5IOC(
        [options["macros"]["motor"] + pv for pv in motor_pvs],
        [options["macros"]["hub"] + pv for pv in hub_pvs], len(mods), **options
    )

def parse_mhubb5(*argv):
    parser, split_args = template_arg_parser(
        desc = "", default_prefix = "mhub_b5:",
        macros = {"motor": "B5:", "hub": "B5:", "mods": "123456"}
    )
    return split_args(parser.parse_args(argv))

if __name__ == "__main__":
    import sys
    ioc_options, run_options = parse_mhubb5(*sys.argv[1:])
    make_mhubb5(**ioc_options).run(**run_options)

