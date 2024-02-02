#!/usr/bin/python3
#
# $ (cd /opt/epics/motorSimIOC/iocBoot/iocMotorSim && \
#       ../../bin/linux-x86_64/motorSim ./st.cmd)
# $ /path/to/raman_ioc.py --list-pvs --prefix B5: \
#       --motor IOC: --hub B5:hv: --nhub 1

from caproto.server import template_arg_parser
from queue_iocs.qioc_seq import QMotorHubIOCBase

groups_b5 = [("mhaydon", "mFocus", 5, 3), ("mopto", "mopto", 2, 15)]

class MhubB5IOCBase(QMotorHubIOCBase):
    def __init__(self, motor_pvs, hub_pvs, **kwargs):
        hubs, minfo = {}, self._motors
        i, j = 0, len(hub_pvs) // len(self._hubs)
        super().__init__(motor_pvs, **kwargs)
        for motor, num in minfo:
            for sub in range(num):
                hubs[(motor, sub)], = self._ectx.get_pvs(hub_pvs[i])
                i += 1
        self._hubs = hubs

    def on_choose(self, motor, sub):
        print(motor, sub)

def make_minfo(nhub, groups = groups_b5):
    minfo = [("%s%d%d" % (group, i, j), nax) for i in range(nhub)
        for group, _, nmtr, nax in groups for j in range(nmtr)]
    motor_pvs = ["m%d" % (i + 1) for i in range(nhub *
        sum(nmtr for _, group, nmtr, nax in groups))]
    hub_pvs = ["BO%d%02dB" % (i, j + 1) for i in range(nhub)
        for j in range(sum(nmtr * nax for _, __, nmtr, nax in groups))]
    return minfo, motor_pvs, hub_pvs

def make_mhubb5(**options):
    nhub = int(options["macros"]["nhub"])
    minfo, motor_pvs, hub_pvs = make_minfo(nhub)
    class MhubB5IOC(MhubB5IOCBase.make_ioc(minfo)):
        _choose_delay1, _choose_delay2 = 0.1, 0.5
        _hubs = ["hub%d" % i for i in range(nhub)]
    return MhubB5IOC(
        [options["macros"]["motor"] + pv for pv in motor_pvs],
        [options["macros"]["hub"] + pv for pv in hub_pvs], **options
    )

def parse_mhubb5(*argv):
    parser, split_args = template_arg_parser(
        desc = "", default_prefix = "mhub_b5:",
        macros = {"motor": "B5:", "hub": "B5:hv:", "nhub": 1}
    )
    return split_args(parser.parse_args(argv))

if __name__ == "__main__":
    import sys
    ioc_options, run_options = parse_mhubb5(*sys.argv[1:])
    make_mhubb5(**ioc_options).run(**run_options)

