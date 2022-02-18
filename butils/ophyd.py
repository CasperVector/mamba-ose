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
	setpoint = Component(EpicsSignalRO, ".VAL")
	offset = Component(EpicsSignalRO, ".OFF", kind = "config")
	offset_dir = Component(EpicsSignalRO, ".DIR", kind = "config")
	offset_freeze_switch = Component(EpicsSignalRO, ".FOFF", kind = "omitted")
	set_use_switch = Component(EpicsSignalRO, ".SET", kind = "omitted")
	velocity = Component(EpicsSignalRO, ".VELO", kind = "config")
	acceleration = Component(EpicsSignalRO, ".ACCL", kind = "config")
	motor_egu = Component(EpicsSignalRO, ".EGU", kind = "config")
	high_limit_switch = Component(EpicsSignalRO, ".HLS", kind = "omitted")
	low_limit_switch = Component(EpicsSignalRO, ".LLS", kind = "omitted")
	high_limit_travel = \
		Component(EpicsSignalRO, ".HLM", kind = "omitted", auto_monitor = True)
	low_limit_travel = \
		Component(EpicsSignalRO, ".LLM", kind = "omitted", auto_monitor = True)
	direction_of_travel = Component(EpicsSignalRO, ".TDIR", kind = "omitted")
	motor_stop = Component(EpicsSignalRO, ".STOP", kind = "omitted")
	home_forward = Component(EpicsSignalRO, ".HOMF", kind = "omitted")
	home_reverse = Component(EpicsSignalRO, ".HOMR", kind = "omitted")
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

