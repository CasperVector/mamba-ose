import threading

class AttrDict(dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__dict__ = self

@property
def masked_attr(obj):
	raise AttributeError

def fn_wait(fs):
	ts = [threading.Thread(target = f, daemon = False) for f in fs]
	[t.start() for t in ts]
	return [t.join() for t in ts]

def input_gen(argv):
	if argv:
		ans = list(reversed(argv))
		def my_input(prompt, default):
			ret = ans.pop()
			print("%s [%s]: %s" % (prompt, default, ret))
			return ret or default
		def end_input():
			assert not ans
	else:
		def my_input(prompt, default):
			return input("%s [%s]: " % (prompt, default)) or default
		def end_input():
			pass
	return my_input, end_input

