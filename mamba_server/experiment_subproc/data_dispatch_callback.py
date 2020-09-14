import struct

from MambaICE import DataFrame, DataType, DataDescriptor
from MambaICE.Dashboard import DataRouterPrx, ScanExitStatus

from bluesky.callbacks.core import CallbackBase, make_class_safe


class DataDispatchCallback(CallbackBase):
    def __init__(self, data_host: DataRouterPrx):
        super().__init__()
        self.data_host = data_host
        self.data_keys = {}
        self.scan_id = 0

    def start(self, doc):
        self.scan_id = doc['scan_id']

    def descriptor(self, doc):
        # TODO: process header, scan metadata, etc
        self.data_keys = keys = doc['data_keys']

        data_descriptors = [
            DataDescriptor(key,
                           self._to_type(des['dtype']),
                           des['shape']) for key, des in keys.items()
        ]
        self.data_host.scanStart(self.scan_id, data_descriptors)

    def event(self, doc):
        data_frames = [
            DataFrame(key,
                      self._pack(self.data_keys[key]['dtype'], num),
                      doc['timestamps'][key]) for key, num in doc['data'].items()
        ]

        self.data_host.pushData(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.scanEnd(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.scanEnd(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.scanEnd(ScanExitStatus.Fail)

    @staticmethod
    def _to_type(string):
        # TODO: move to elsewhere
        if string == 'number':
            return DataType.Float
        elif string == 'string':
            return DataType.String
        elif string == 'integer':
            return DataType.Integer

    @staticmethod
    def _pack(_type, value):
        if _type == 'number':
            return struct.pack("d", float(value))
        elif _type == 'integer':
            return struct.pack("i", int(value))
        elif _type == 'string':
            return value.encode('utf-8')
