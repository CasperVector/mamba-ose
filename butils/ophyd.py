import threading
import time
import traceback
from enum import Enum
from ophyd import Device, Component, EpicsSignal, EpicsSignalRO, \
    EpicsMotor, PositionerBase, PVPositioner, PVPositionerPC
from ophyd.device import required_for_connection
from ophyd.signal import AttributeSignal
from ophyd.status import wait as status_wait
from ophyd.utils.epics_pvs import AlarmSeverity, \
   data_shape, data_type, raise_if_disconnected
from .common import AttrDict, fn_wait, masked_attr

class HomeEnum(str, Enum):
    forward, reverse, fwdlimit, revlimit = \
        "forward", "reverse", "fwdlimit", "revlimit"

def cpt_to_dev(cpt, name):
    return cpt.cls(name = name, **cpt.kwargs) if cpt.suffix is None \
        else cpt.cls(cpt.suffix, name = name, **cpt.kwargs)

def para_move(mposs):
    try:
        assert fn_wait([m.set(p).wait for m, p in mposs.items()])
    except KeyboardInterrupt:
        assert fn_wait([m.stop for m in mposs], abort = False)
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
    motor_done_move = Component(EpicsSignalRO, ".DMOV",
        kind = "omitted", auto_monitor = True)
    jog_forward, jog_reverse = [Component(EpicsSignal, suffix,
        kind = "omitted", auto_monitor = True) for suffix in [".JOGF", ".JOGR"]]
    _homing_direction, _homing_directions = "", ("fwdlimit", "revlimit")

    def _move_changed_base(self, timestamp, done, **kwargs):
        was_moving, self._moving, started = self._moving, not done, False
        if not self._started_moving:
            started = self._started_moving = (not was_moving and self._moving)
        if started:
            self._run_subs(sub_type = self.SUB_START,
                timestamp = timestamp, value = done, **kwargs)
        elif was_moving and not self._moving:
            success = True
            if self.direction_of_travel.get():
                if self.high_limit_switch.get(use_monitor = False) \
                    and self._homing_direction != "fwdlimit":
                    success = False
            else:
                if self.low_limit_switch.get(use_monitor = False) \
                    and self._homing_direction != "revlimit":
                    success = False
            severity = self.readback.alarm_severity
            if severity != AlarmSeverity.NO_ALARM and \
                severity > self.tolerated_alarm:
                success = False
            self._homing_direction = ""
            self._done_moving(success = success,
                timestamp = timestamp, value = done)

    @required_for_connection
    @motor_done_move.sub_value
    def _move_changed(self, timestamp = None,
        value = None, sub_type = None, **kwargs):
        if not self._homing_direction and value is not None:
            self._move_changed_base(timestamp, bool(value))

    @jog_forward.sub_value
    def _jogf_changed(self, timestamp = None, value = None, **kwargs):
        if self._homing_direction == "fwdlimit" and value is not None:
            self._move_changed_base(timestamp, not value)

    @jog_reverse.sub_value
    def _jogr_changed(self, timestamp = None, value = None, **kwargs):
        if self._homing_direction == "revlimit" and value is not None:
            self._move_changed_base(timestamp, not value)

    @raise_if_disconnected
    def move(self, position, wait = True, **kwargs):
        self._started_moving, self._homing_direction = False, ""
        status = PositionerBase.move(self, position, **kwargs)
        self.setpoint.put(position, wait = False)
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status

    @raise_if_disconnected
    def home(self, direction, wait = True, **kwargs):
        sig = getattr(self, {
            HomeEnum.forward: "home_forward",
            HomeEnum.reverse: "home_reverse",
            HomeEnum.fwdlimit: "jog_forward",
            HomeEnum.revlimit: "jog_reverse",
        }[HomeEnum(direction)])
        self._started_moving, self._homing_direction = False, \
            direction if direction in self._homing_directions else ""
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
        self._event.set()

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.readback.name = self.name

class HREnergy(MonoEnergy):
    auto = Component(EpicsSignal, "ModeBO", kind = "omitted")

    def __init__(self, prefix = "", *, name, resetter,
        delta = (1.0, 1e-5), settle_time = None, timeout = None, **kwargs):
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

class SerialEnergy(PositionerBase):
    egu, _stopping = "", False

    def __init__(self, *args, motors, **kwargs):
        super().__init__(*args, **kwargs)
        self._motors = motors
        self._name_map = AttrDict\
            ((m.vname().split(".", 1)[-1], m) for m in motors)

    def read(self, dot = False):
        return dict([(self.vname(dot),
            {"value": self.position, "timestamp": time.time()})])

    def describe(self, dot = False):
        return dict([(self.vname(dot), {
            'source': "ENERGY:%s" % type(self).__name__,
            'dtype': data_type(self.position),
            'shape': data_shape(self.position),
        })])

    def read_configuration(self, dot = False, fast = False):
        return {}

    def describe_configuration(self, dot = False):
        return {}

    def stop(self, *, success = False):
        self._stopping = True
        assert fn_wait([
            (lambda m: lambda: m.stop(success = success))(m)
            for m in self._motors
        ], abort = False)

    def _para_move(self, pos, motors):
        def waiter(m):
            m = self._name_map.get(m, m)
            assert hasattr(m, "move"), m
            return lambda: m.move(pos[m])
        assert fn_wait([waiter(m) for m in motors])
        if self._stopping:
            raise StopIteration()

    def _move(self, value):
        pass

    def _move_base(self, value):
        success = True
        try:
            self._move(value)
        except Exception as e:
            if not isinstance(e, StopIteration):
                # With `raise', the .wait() traceback would get mixed up here.
                traceback.print_exc()
                success = False
        finally:
            self._moving = False
            self._set_position(value)
            self._done_moving(success = success,
                timestamp = time.time(), value = value)

    def move(self, value, *, wait = True, timeout = None, moved_cb = None):
        status = super().move(value, timeout = timeout, moved_cb = moved_cb)
        self._run_subs(sub_type = self.SUB_START, timestamp = time.time())
        self._moving, self._stopping = True, False
        threading.Thread(daemon = True,
            target = self._move_base, args = (value,)).start()
        try:
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status

class LinearEnergy(SerialEnergy):
    _energy_unit, _energy_tol = 1e3, 1e-2

    def __init__(self, *args, energy = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._energy, self._mode = energy, None
        self._calib_map = {}

    def _find(self, emap, value, approx = False):
        for i, (v, pos) in enumerate(emap):
            if value <= v:
                break
        else:
            i = len(emap)
        if not approx:
            return i
        if i and abs(value - emap[i - 1][0]) <= self._energy_tol:
            return i - 1, True
        if i < len(emap) and abs(value - emap[i][0]) <= self._energy_tol:
            return i, True
        return i, False

    def calibrate(self, value = None, mode = None):
        empty = value is None and mode is not None
        if value is None:
            value = self._energy and self._energy.position * self._energy_unit
        if mode is None:
            mode = self._mode
        assert mode is not None and (value is not None or empty)
        self._mode, emap = mode, self._calib_map.setdefault(mode, [])
        if empty:
            return
        i, close = self._find(emap, value, approx = True)
        pos = [value / self._energy_unit if m == self._energy
            else m.position for m in self._motors]
        if close:
            emap[i] = (value, pos)
        else:
            emap.insert(i, (value, pos))

    def uncalibrate(self, value = None, mode = None):
        if value is None:
            self._calib_map.pop(mode)
        else:
            emap = self._calib_map[self._mode if mode is None else mode]
            i, close = self._find(emap, value, approx = True)
            assert close
            emap.pop(i)

    def _pos(self, value):
        emap = self._calib_map[self._mode]
        n = len(emap)
        if not n:
            return {m: m.position for m in self._motors}
        elif n == 1:
            return {m: p for m, p in zip(self._motors, emap[0][1])}
        i = max(0, min(n - 2, self._find(emap, value) - 1))
        x = (emap[i + 1][0] - value) / (emap[i + 1][0] - emap[i][0])
        return {m: x * p0 + (1.0 - x) * p1 for m, p0, p1 in zip
            (self._motors, emap[i][1], emap[i + 1][1])}

    def _move(self, value):
        pos = self._pos(value)
        self._para_move(pos, list(pos))

