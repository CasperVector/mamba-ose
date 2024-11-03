import collections
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
    def __init__(self, table):
        CallbackBase.__init__(self)
        self.table, self.num = table, len(table)
        self.steps = dict(collections.Counter(table))
        self.steps[table[0]] -= 1

    def key(self, idx):
        return self.table[idx]

    def start(self, doc):
        self.idx, self.prev = 0, None
        self.progress = {k: [0, 0.0] for k in self.steps}

    def eta(self, diff):
        prog = self.progress[self.key(self.idx)]
        prog[0], prog[1] = prog[0] + 1, prog[1] + diff
        used, remain, nul = 0.0, 0.0, 0
        for key in self.progress:
            step, prog = self.steps[key], self.progress[key]
            if prog[0]:
                used += prog[1]
                remain += prog[1] / prog[0] * (step - prog[0])
            else:
                nul += step
        return remain + used / self.idx * nul

    def event(self, doc):
        prev, self.prev = self.prev, doc["time"]
        diff = None if prev is None else self.prev - prev
        eta = None if diff is None else self.eta(diff)
        self.idx = self.idx + 1
        self.reporter.report(self.idx / self.num,
            None if eta is None else self.prev + eta)

    def stop(self, doc):
        self.reporter.progress = None

class ProgressSimple(ProgressBase):
    def __init__(self, *nums):
        CallbackBase.__init__(self)
        self.nums, gaps = nums, [1]
        for n in reversed(self.nums):
            gaps.append(gaps[-1] * n)
        self.gaps, self.num = gaps[-2 :: -1], gaps[-1]
        self.steps = {i: self.num // gap for i, gap in enumerate(self.gaps)}
        for i in range(len(self.nums) - 1, 0, -1):
            self.steps[i] -= self.steps[i - 1]
        self.steps[0] -= 1

    def key(self, idx):
        for i, gap in enumerate(self.gaps):
            if not idx % gap:
                return i

def expand_simple(nums):
    ret = []
    for i, n in reversed(list(enumerate(nums))):
        ret = ([i] + ret[1:]) * n
    return ret

progressBars = {"base": ProgressBase, "simple": ProgressSimple}

