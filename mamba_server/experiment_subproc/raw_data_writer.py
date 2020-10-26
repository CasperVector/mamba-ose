import os
from typing import List

import mamba_server.experiment_subproc
from mamba_server.file_writer import H5FileWriter
from utils.data_utils import DataDescriptor, data_frame_to_value


class RawDataWriter:
    def __init__(self, dir, prefix, pattern):
        self.ongoing_scan_id = 0
        self.writer = None

        self.dir = dir
        self.prefix = prefix
        self.pattern = pattern

        self.data_items = None

    def scan_start(self, _id, data_descriptors: List[DataDescriptor]):
        self.ongoing_scan_id = _id
        name = self.pattern.format(prefix=self.prefix,
                                   scan_id=_id,
                                   session=mamba_server.session_start_at)
        path = os.path.join(self.dir, name)
        self.writer = H5FileWriter(path)

        self.writer.add_section("data")

        self.data_items = {des.name: des for des in data_descriptors}
        for des in data_descriptors:
            self.writer.add_dataset("data",
                                    des.name,
                                    des.type,
                                    [1] + des.shape,
                                    [None] + des.shape)

    def scan_end(self, status):
        if self.writer:
            self.writer.close_file()
        self.ongoing_scan_id = -1

    def data_update(self, frames):
        if self.ongoing_scan_id > 0:
            for frame in frames:
                self.writer.append_data("data", frame.name,
                                        data_frame_to_value(frame))
