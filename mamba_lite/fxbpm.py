import collections
import datetime
import epics
import numpy
from butils.gutils import QueueServer, err_state
from mamba.attitude.common import roi_crop, \
    norm_roi, roi2xywh, xywh2roi, proj_peak, img_peak

def auto_roi(img, ratio = (2.5, 5.0)):
    roi = tuple()
    for i in [0, 1]:
        proj = img.sum(i)
        pos, lohi = proj_peak(proj)
        ratios = ratio[1],
        if lohi[0] < pos:
            ratios += pos / (pos - lohi[0]),
        if pos < lohi[1]:
            ratios += (img.shape[1 - i] - 1 - pos) / (lohi[1] - pos),
        roi += tuple(pos - (pos - v) * max(ratio[0], min(ratios)) for v in lohi)
    return norm_roi(roi, *img.shape[::-1])

def img_bpm(img, roi):
    crop = roi_crop(img, roi)
    total = crop.sum()
    if total:
        idxs = [numpy.arange(crop.shape[1 - i]) for i in [0, 1]]
        x, y = [(idxs[i] * crop.sum(i)).sum() / total for i in [0, 1]]
    else:
        x, y = (roi[0] + roi[1]) / 2, (roi[2] + roi[3]) / 2
    total, area = img_peak(crop)[2]
    return roi[0] + x, roi[2] + y, (total / area if area else 0.0)

def fmt_pos(x):
    return "%.5g" % x

def fmt_time(t):
    return datetime.datetime.utcfromtimestamp(t).\
        strftime("%Y-%m-%dT%H:%M:%S.%fZ")

class FxBpmServer(QueueServer):
    pv = record = psize = span = None
    push = False

    def open(self, prefix, psize, record = "record.txt", span = 250.0):
        assert not self.pv
        epics.caput(prefix + "cam1:ImageMode", "Continuous")
        epics.caput(prefix + "cam1:ArrayCallbacks", 1)
        epics.caput(prefix + "image1:EnableCallbacks", 1)
        try:
            epics.caput(prefix + "cam1:Acquire", 1)
            self.shape = epics.caget(prefix + "cam1:SizeY_RBV"), \
                epics.caget(prefix + "cam1:SizeX_RBV")
            assert all(self.shape)
            self.pv = epics.PV(prefix + "image1:ArrayData",
                count = self.shape[0] * self.shape[1], auto_monitor = True)
            self.pv.add_callback(self.icb)
            self.record = open(record, "a")
        except:
            self.close()
            raise
        self.psize, self.span = psize, span
        return ()

    def close(self):
        if self.record:
            self.record.close()
        if self.pv:
            self.pv.clear_callbacks()
            try:
                epics.caput(self.pv.pvname[:-16] + "cam1:Acquire", 0)
            except:
                pass
        self.pv = self.record = None

    def icb(self, *, value, timestamp, **kwargs):
        if self.push:
            self.push = False
            img = value.reshape(self.shape)
            self.request("_data", img, timestamp)

    def ijxy(self, ij):
        x = self.psize * (ij[0] - 0.5 * self.shape[1])
        y = self.psize * (0.5 * self.shape[0] - ij[1])
        return ij + (x, y)

    def bpm(self, img, roi, time, plot):
        i, j, c = img_bpm(img, roi)
        x, y = self.ijxy((i, j))[2:]
        self.record.write\
            (" ".join([fmt_time(time), fmt_pos(x), fmt_pos(y)]) + "\n")
        plot.append((time, x, y))
        while plot[0][0] < time - self.span:
            plot.popleft()
        return (i, j, x, y, c), numpy.array(plot).T

    def serve(self):
        img, time, roi, plot = None, None, None, collections.deque()
        while True:
            reply, req = self.get_req()
            if req[0] in ["exit", "close"]:
                reply("", "close")
                break
            elif req[0] == "roi" and img is not None:
                if len(req) > 1:
                    roi = norm_roi(xywh2roi(req[1]), *self.shape[::-1]) \
                        if req[1] else auto_roi(img)
                reply("", "roi", roi2xywh(roi))
            elif req[0] in ["_data", "update"] or \
                (req[0] == "start" and img is not None):
                reply("", *req)
            else:
                err_state(reply)
            if req[0] == "_data":
                img, time = req[1:]
                self.notify("img", img, time)
                if not roi:
                    roi = auto_roi(img)
                self.notify("bpm", *self.bpm(img, roi, time, plot))
            elif req[0] == "update":
                self.push = True

            if req[0] != "start":
                continue
            while True:
                if self.q.empty():
                    self.push = True
                reply, req = self.get_req()
                if req[0] in ["exit", "stop"]:
                    reply("", "stop")
                    break
                elif req[0] == "_data":
                    reply("", *req)
                    img, time = req[1:]
                    self.notify("img", img, time)
                    self.notify("bpm", *self.bpm(img, roi, time, plot))
                elif req[0] == "roi" and len(req) == 1:
                    reply("", "roi", roi2xywh(roi))
                else:
                    err_state(reply)
            self.notify("img", img, time)

