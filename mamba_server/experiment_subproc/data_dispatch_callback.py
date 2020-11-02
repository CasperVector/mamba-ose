from utils.data_utils import string_to_type, to_data_frame

from MambaICE import (DataType, DataDescriptor, TypedDataFrame, StringDataFrame,
                      FloatDataFrame, IntegerDataFrame, ArrayDataFrame)
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

        for key in keys.keys():
            keys[key]['dtype'] = string_to_type(keys[key]['dtype'])

        data_descriptors = [
            DataDescriptor(key,
                           "",
                           des['dtype'],
                           des['shape']) for key, des in keys.items()
        ]
        self.data_host.scanStart(self.scan_id, data_descriptors)

    def event(self, doc):
        data_frames = []
        for key, value in doc['data'].items():
            if 'external' in self.data_keys[key]:
                continue
            data_frames.append(
                to_data_frame(
                    key,
                    "",
                    self.data_keys[key]['dtype'],
                    value,
                    doc['timestamps'][key])
            )

        self.data_host.pushData(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.scanEnd(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.scanEnd(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.scanEnd(ScanExitStatus.Fail)
