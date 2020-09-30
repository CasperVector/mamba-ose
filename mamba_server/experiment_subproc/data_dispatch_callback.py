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
        for key in doc.keys():
            doc[key]['dtype'] = string_to_type(doc[key]['dtype'])

        self.data_keys = keys = doc['data_keys']
        data_descriptors = [
            DataDescriptor(key,
                           des['dtype'],
                           des['shape']) for key, des in keys.items()
        ]
        self.data_host.scanStart(self.scan_id, data_descriptors)

    def event(self, doc):
        data_frames = [
            to_data_frame(
                key,
                self.data_keys[key]['dtype'],
                value,
                doc['timestamps'][key]) for key, value in doc['data'].items()
        ]

        self.data_host.pushData(data_frames)

    def stop(self, doc):
        if doc['exit_status'] == 'success':
            self.data_host.scanEnd(ScanExitStatus.Success)
        elif doc['exit_status'] == 'abort':
            self.data_host.scanEnd(ScanExitStatus.Abort)
        elif doc['exit_status'] == 'fail':
            self.data_host.scanEnd(ScanExitStatus.Fail)
