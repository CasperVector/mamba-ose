from bluesky.callbacks.core import CallbackBase

class ProgressReporter(object):
    def __init__(self, bars, notify):
        self.bars, self.notify = bars, notify
        self.progress = None

    def __call__(self, name, doc):
        if name == "start":
            self.progress = None
            progress = doc.get("hints", {}).get("progress")
            if progress and progress[0] in self.bars:
                self.progress = self.bars[progress[0]](*progress[1:])
                self.progress.reporter = self
        if self.progress:
            self.progress(name, doc)

    def report(self, progress, eta):
        self.notify({"typ": "scan/progress",
            "progress": progress, "eta": eta})

class ProgressBase(CallbackBase):
    def stop(self, doc):
        self.reporter.progress = None

class ProgressSimple(ProgressBase):
    def __init__(self, *nums):
        super().__init__()
        self.nums = nums

    def start(self, doc):
        self.scan, self.prev = doc["scan_id"], None
        self.idx, self.progress = 0, [[0, 0.0] for n in self.nums]
        gaps = [1]
        for n in reversed(self.nums):
            gaps.append(gaps[-1] * n)
        self.steps, self.num = list(reversed(gaps[:-1])), gaps[-1]
        self.steps = [[self.num // gap, gap] for gap in self.steps]
        for i in range(len(self.nums)):
            self.steps[i][0] -= sum(step[0] for step in self.steps[:i])
        self.steps[0][0] -= 1

    def event(self, doc):
        self.idx, cur = self.idx + 1, doc["time"]
        percent = self.idx / self.num
        if self.idx == 1:
            self.prev = cur
            self.reporter.report(percent, None)
            return
        for i, step in enumerate(self.steps):
            if not (self.idx - 1) % step[1]:
                break
        self.progress[i][0] += 1
        self.progress[i][1] += cur - self.prev
        delta, self.prev = 0.0, cur
        for step, prog in zip(self.steps, self.progress):
            if prog[0]:
                delta += prog[1] / prog[0] * (step[0] - prog[0])
        self.reporter.report(percent, cur + delta)

progressBars = {"simple": ProgressSimple}

