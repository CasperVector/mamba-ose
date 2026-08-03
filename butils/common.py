import functools
import glob
import os
import queue
import re
import sys
import threading
from collections.abc import Sequence
try:
    import cbor2
    import numpy
except ImportError:
    pass

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

def fn_wait(fs, abort = True):
    q, ret = queue.Queue(), [None] * len(fs)
    def wrap(i, f):
        try:
            q.put((i, f()))
        except Exception as e:
            q.put((e, None))
            raise
    ts = [threading.Thread(target = wrap, args = (i, f), daemon = True)
        for i, f in enumerate(fs)]
    [t.start() for t in ts]
    for f in fs:
        msg = q.get()
        if isinstance(msg[0], Exception):
            if not abort:
                [t.join() for t in ts]
            return
        ret[msg[0]] = msg[1]
    [t.join() for t in ts]
    return ret

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

cbor_decoder_types = {
    64: "u1", 65: ">u2", 66: ">u4", 67: ">u8", 68: "u1", 69: "<u2",
    70: "<u4", 71: "<u8", 72: "i1", 73: ">i2", 74: ">i4", 75: ">i8",
    77: "<i2", 78: "<i4", 79: "<i8", 80: ">f2", 81: ">f4",
    82: ">f8", 83: ">f16", 84: "<f2", 85: "<f4", 86: "<f8", 87: "<f16",
}
cbor_encoder_types = {cbor_decoder_types[v]: v
    for v in cbor_decoder_types if v != 68}

def tag_decoder_numpy(decoder, tag):
    if isinstance(tag, bool):
        tag = decoder
    if tag.tag in cbor_decoder_types:
        return numpy.frombuffer(tag.value, dtype = cbor_decoder_types[tag.tag])
    if tag.tag in [40, 1040]:
        assert (
            isinstance(tag.value, Sequence) and len(tag.value) == 2 and
            isinstance(tag.value[0], Sequence) and
            isinstance(tag.value[1], numpy.ndarray)
        ), tag.value
        return tag.value[1].reshape\
            (tag.value[0], order = "C" if tag.tag == 40 else "F")
    return tag

# <https://github.com/gsmecher/tuberd/blob/master/tuber/codecs.py>

def default_encoder_numpy(encoder, obj):
    if isinstance(obj, (numpy.number, numpy.bool_)):
        return encoder.encode(obj.item())
    assert isinstance(obj, numpy.ndarray), obj
    dtype, flags = obj.dtype, obj.flags
    assert flags.c_contiguous or flags.f_contiguous, obj
    dtype = dtype.byteorder, dtype.kind, dtype.itemsize
    dtype = cbor_encoder_types["%s%s%d" % ((
        "" if dtype[2] == 1 else
        (dtype[0] if dtype[0] in "<>" else
        "<>"[sys.byteorder == "big"]),
    ) + dtype[1:])]
    encoder.encode_length(6, 40 if flags.c_contiguous else 1040)
    encoder.encode_length(4, 2)
    encoder.encode_length(4, len(obj.shape))
    for n in obj.shape:
        encoder.encode_int(n)
    encoder.encode_length(6, dtype)
    encoder.encode_length(2, obj.nbytes)
    encoder.fp.write(obj.data)

def cbor_load_numpy(buf):
    return cbor2.loads(buf, tag_hook = tag_decoder_numpy)

def cbor_dump_numpy(obj):
    return cbor2.dumps(obj, default = default_encoder_numpy)

