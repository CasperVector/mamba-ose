import time
from enum import Enum
from ophyd import Device, Component, EpicsSignal, EpicsSignalRO, \
    EpicsMotor, PositionerBase, PVPositioner, PVPositionerPC
from ophyd.signal import AttributeSignal
from ophyd.status import wait as status_wait
from ophyd.utils.epics_pvs import raise_if_disconnected
from .common import fn_wait, masked_attr

class HomeEnum(str, Enum):
    forward, reverse, poslimit, neglimit = \
        "forward", "reverse", "poslimit", "neglimit"

def cpt_to_dev(cpt, name):
    return cpt.cls(name = name, **cpt.kwargs) if cpt.suffix is None \
        else cpt.cls(cpt.suffix, name = name, **cpt.kwargs)

def para_move(mposs):
    try:
        assert fn_wait([m.set(p).wait for m, p in mposs.items()])
    except KeyboardInterrupt:
        assert fn_wait([m.stop for m in mposs])
        raise

class ThrottleMonitor(Device):
    monitor_period, _monitor_period = Component(AttributeSignal,
        attr = "_monitor_period", kind = "config"), 0.0

    def maybe_monitor(self, _timestamp, timestamp):
        if timestamp < _timestamp[0] + self._monitor_period:
            return False
        _timestamp[0] = timestamp
        return True

class SimpleDet(Device):
    value = Component(EpicsSignalRO, "")

class MonitorMotor(ThrottleMonitor):
    def monitor(self, dnotify):
        _timestamp = [0.0]
        def cb(*, value, timestamp, **kwargs):
            if value is not None and self.maybe_monitor(_timestamp, timestamp):
                dnotify("monitor/position", {
                    "data": {self.name: value},
                    "timestamps": {self.name: timestamp}
                })
        return self.subscribe(cb)

class MyEpicsMotor(MonitorMotor, EpicsMotor):
    motor_stop, home_forward, home_reverse, jog_forward, jog_reverse = \
        [Component(EpicsSignal, suffix, kind = "omitted")
            for suffix in [".STOP", ".HOMF", ".HOMR", ".JOGF", ".JOGR"]]

    @raise_if_disconnected
    def home(self, direction, wait = True, **kwargs):
        sig = getattr(self, {
            HomeEnum.forward: "home_forward",
            HomeEnum.reverse: "home_reverse",
            HomeEnum.poslimit: "jog_forward",
            HomeEnum.neglimit: "jog_reverse",
        }[HomeEnum(direction)])
        self._started_moving = False
        position = (self.low_limit + self.high_limit) / 2
        status = PositionerBase.move(self, position, **kwargs)
        sig.put(1, wait = False)
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status

class EpicsMotorRO(MyEpicsMotor):
    setpoint = Component(EpicsSignalRO, ".VAL", auto_monitor = True)
    offset, offset_dir, velocity, acceleration, motor_egu, motor_eres = \
        [Component(EpicsSignalRO, suffix, kind = "config", auto_monitor = True)
            for suffix in [".OFF", ".DIR", ".VELO", ".ACCL", ".EGU", ".ERES"]]
    offset_freeze_switch, set_use_switch, \
        high_limit_travel, low_limit_travel, direction_of_travel = \
        [Component(EpicsSignalRO, suffix, kind = "omitted", auto_monitor = True)
            for suffix in [".FOFF", ".SET", ".HLM", ".LLM", ".TDIR"]]
    motor_stop, home_forward, home_reverse = \
        [Component(EpicsSignalRO, suffix, kind = "omitted")
            for suffix in [".STOP", ".HOMF", ".HOMR"]]
    stop = move = set_current_position = home = set_lim = masked_attr

class ErrorPositioner(PVPositioner):
    error, error_value = None, 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.error is not None
        self._event, self._error = threading.Event(), True

    def move(self, position, wait = True, timeout = None, moved_cb = None):
        self.stop_signal.wait_for_connection()
        self._event.clear()
        self._error = True
        try:
            status = PositionerBase.move\
                (self, position, timeout = timeout, moved_cb = moved_cb)
            self._setup_move(position)
            self._error = self.error.get() == self.error_value
        finally:
            self._event.set()
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status

    def _done_moving(self, success = True,
        timestamp = None, value = None, **kwargs):
        if not self._event.wait(timeout = 1.0) or self._error:
            success = False
        if success:
            self._run_subs(sub_type = self.SUB_DONE,
                timestamp = timestamp, value = value)
        self._run_subs(sub_type = self._SUB_REQ_DONE,
            success = success, timestamp = timestamp)
        self._reset_sub(self._SUB_REQ_DONE)

class QueueMotor(MonitorMotor, ErrorPositioner):
    setpoint = Component(EpicsSignal, "val")
    readback = Component(EpicsSignalRO, "rbv",
        kind = "hinted", auto_monitor = True)
    done = stop_signal = Component(EpicsSignal, "dmov",
        kind = "omitted", auto_monitor = True)
    error = Component(EpicsSignal, "err", kind = "omitted")
    done_value = stop_value = error_value = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.readback.name = self.name

class MonoEnergy(PVPositionerPC):
    setpoint = Component(EpicsSignal, "EAO")
    readback = Component(EpicsSignalRO, "ERdbkAO",
        kind = "hinted", auto_monitor = True)
    auto = Component(EpicsSignal, "ModeBO", kind = "omitted")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.readback.name = self.name

class HREnergy(MonoEnergy):
    def __init__(self, prefix = "", *, name, resetter,
        delta = (1, 1e-5), settle_time = None, timeout = None, **kwargs):
        super().__init__(prefix = prefix, name = name,
            settle_time = settle_time, timeout = timeout, **kwargs)
        self.resetter, self.delta = resetter, delta

    def reset(self):
        self.resetter.set(self.resetter.position + self.delta[0]).wait()
        self.setpoint.put(self.position + self.delta[1])
        time.sleep(self.settle_time)
        self.auto.set(1).wait()

    def stage(self):
        super().stage()
        self.reset()

