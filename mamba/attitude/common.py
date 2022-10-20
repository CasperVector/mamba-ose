import cv2
import h5py
import numpy
import os

def roi_slice(img, roi):
    return img[roi[2] : roi[3], roi[0] : roi[1]]

def norm_roi(roi, w, h):
    x0, x1, y0, y1 = map(int, numpy.clip(roi, 0, (w, w, h, h)))
    return (x0, x1, y0, y1) if x0 < x1 and y0 < y1 else (0, w, 0, h)

def norm_origin(origin, w, h):
    return tuple(map(int, numpy.clip(origin, 0, (w, h))))

def roi2xywh(roi):
    x0, x1, y0, y1 = roi
    return x0, y0, x1 - x0, y1 - y0

def xywh2roi(xywh):
    x, y, w, h = xywh
    return x, x + w, y, y + h

def auto_contours(img, threshold):
    img = cv2.GaussianBlur(img, (0, 0), cv2.BORDER_DEFAULT)
    mask = (img >= threshold).astype("uint8")
    ret = [xywh2roi(cv2.boundingRect(contour)) for contour in
        cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]]
    ret = sorted((-roi_slice(img, roi).sum(), roi) for roi in ret)
    return [roi for total, roi in ret]

def img_phist(img, origin, nbins):
    h, w = img.shape
    coords = numpy.full((h, w), numpy.arange(w) - origin[0]) * (1 + 0j)
    coords += numpy.full((w, h), origin[1] - numpy.arange(h)).T * (0 + 1j)
    rads, thetas = numpy.abs(coords), numpy.angle(coords)
    thetas[thetas < 0] += 2 * numpy.pi
    ret = ()
    if any(nbins):
        img = img.astype(float)
    if nbins[0]:
        bins = numpy.arange(nbins[0] + 1) / nbins[0] * rads.max()
        hist = numpy.histogram(rads, bins, weights = img)[0] / \
            numpy.histogram(rads, bins)[0]
        hist[numpy.isfinite(hist)] = 0
        ret += hist, bins
    if nbins[1]:
        bins = numpy.arange(nbins[1] + 1) / nbins[1] * (2 * numpy.pi)
        ret += numpy.histogram(thetas, bins, weights = img)
    if not ret:
        ret = rads, thetas
    return ret

class AttiAdMixin(object):
    bad_threshold = 0

    def __init__(self, mzcb = None):
        self.ad = self.devices = self.dataset = None
        if mzcb:
            self.send_event = lambda doc: mzcb("event", doc)

    def stage(self):
        assert self.ad, "need set_devices()"
        if self.dataset:
            return
        self.ad.stage()
        f = h5py.File(self.ad.hdf1.full_file_name.get(), "r", swmr = True)
        self.dataset = f["entry/data/data"]

    def unstage(self, clean = True):
        assert self.ad, "need set_devices()"
        if not self.dataset:
            return
        self.ad.unstage()
        f = self.dataset.file.filename
        self.dataset.file.close()
        self.dataset = None
        if clean:
            os.remove(f)

    def acquire(self):
        key, data = self.ad.name + "_image", {}
        self.ad.trigger().wait()
        [data.update(dev.read()) for dev in self.devices]
        data, timestamps = [{k: data[k][field] for k in data}
            for field in ["value", "timestamp"]]
        self.dataset.refresh()
        data[key] = numpy.array(self.dataset[-1])
        img = data[key].copy()
        if self.bad_threshold:
            img[img > self.bad_threshold] = 0
        doc = {"data": data, "timestamps": timestamps}
        return doc, img

