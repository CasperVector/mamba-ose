import base64
import pickle
from .zserver import ZnClient

class MnClient(ZnClient):
    handles = ZnClient.handles + ["doc", "scan"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subs = {typ: [] for typ in self.handles}

    def do_doc(self, msg):
        msg["doc"] = pickle.loads(base64.b64decode(msg["doc"].encode("UTF-8")))
        for sub in self.subs["doc"]:
            sub(msg)

    def do_scan(self, msg):
        for sub in self.subs["scan"]:
            sub(msg)

