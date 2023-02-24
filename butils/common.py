import threading

class AttrDict(dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__dict__ = self

@property
def masked_attr(obj):
	raise AttributeError

def fn_wait(fs):
	ret = [None] * (len(fs) + 1)
	def wrap(i, f):
		try:
			ret[i] = f()
		except Exception as e:
			ret[-1] = e
			raise
	ts = [threading.Thread(target = wrap, args = (i, f), daemon = True)
		for i, f in enumerate(fs)]
	[t.start() for t in ts]
	[t.join() for t in ts]
	return None if ret[-1] else ret[:-1]

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

