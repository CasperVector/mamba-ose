import functools
import glob
import os
import re
import threading

class AttrDict(dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__dict__ = self

@property
def masked_attr(obj):
	raise AttributeError

def strverscmp(s1, s2):
	for i, (c1, c2) in enumerate(zip(s1, s2)):
		if c1 != c2:
			break
	else:
		return len(s1) - len(s2)
	t1, t2 = s1[i:], s2[i:]
	m0 = re.search("[0-9]*$", s1[:i]).group(0)
	m1, m2 = [re.match("[0-9]*", t).group(0) for t in [t1, t2]]
	m1, m2 = m0 + m1, m0 + m2
	if m1 and m2:
		d = int(m1) - int(m2)
		if d:
			return d
	return ord(t1[0]) - ord(t2[0])

strverskey = functools.cmp_to_key(strverscmp)

def user_glob(*ss):
	return sorted(sum([glob.glob(os.path.expanduser(s))
		for s in ss], []), key = strverskey)

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

