import functools
import glob
import os
import queue
import re
import sys
import threading
import traceback
from collections.abc import Sequence
from concurrent import futures
try:
    import cbor2
except ImportError:
    pass
try:
    import numpy
except ImportError:
    pass

def partition(f, l):
    ret = [], []
    for x in l:
        ret[not f(x)].append(x)
    return ret

def fill_elems(d, l):
    return [d[k] for k in l if k in d]

def fill_keys(d, l):
    return [(d[k], v) for k, v in l if k in d]

def fill_vals(d, l):
    return [(k, d[v]) for k, v in l if v in d]

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

# Backported from Python 3.9.
def threadpool_shutdown(obj, wait = True, *, cancel_futures = False):
    with obj._shutdown_lock:
        obj._shutdown = True
        if cancel_futures:
            while True:
                try:
                    work_item = obj._work_queue.get_nowait()
                except queue.Empty:
                    break
                if work_item is not None:
                    work_item.future.cancel()
        obj._work_queue.put(None)
    if wait:
        for t in obj._threads:
            t.join()

def fn_wait(fs, abort = False, jobs = None):
    ret = [None] * len(fs), [None] * len(fs)
    lock = threading.Lock()
    def wrap(i, f):
        try:
            ret[0][i] = f()
            return 0
        except Exception as e:
            ret[1][i] = e
            with lock:
                traceback.print_exc()
            return 1
    executor = futures.ThreadPoolExecutor(max_workers = jobs)
    ss = [executor.submit(wrap, i, f) for i, f in enumerate(fs)]
    for s in futures.as_completed(ss):
        if s.result() and abort:
            break
    executor.shutdown(wait = False, cancel_futures = True)
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

unsign_map = {numpy.dtype(k): numpy.dtype(k.replace("i", "u"))
    for k in ["i1", ">i2", ">i4", ">i8", "<i2", "<i4", "<i8"]}

def unsign(img):
    return img.view(unsign_map.get(img.dtype, img.dtype))

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

