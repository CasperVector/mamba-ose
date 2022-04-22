import math
import threading
import time
from ophyd import Device, Component, \
	EpicsSignal, EpicsSignalRO, EpicsMotor, PVPositionerPC
from ophyd.signal import AttributeSignal
from ophyd.status import Status
from .common import masked_attr

def cpt_to_dev(cpt, name):
	return cpt.cls(name = name, **cpt.kwargs) if cpt.suffix is None \
		else cpt.cls(cpt.suffix, name = name, **cpt.kwargs)

class SimpleDet(Device):
	value = Component(EpicsSignalRO, "")

class EpicsMotorRO(EpicsMotor):
	setpoint = Component(EpicsSignalRO,
		".VAL", limits = True, auto_monitor = True)
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

