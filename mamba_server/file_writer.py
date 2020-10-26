from typing import List
from abc import ABC
import h5py
import numpy as np
import os
from pathlib import Path

import Ice
import MambaICE
import mamba_server
from .data_router import DataClientCallback
from .device_manager import DeviceManagerI
from .data_router import DataRouterI
from utils.data_utils import data_frame_to_value, DataType, DataDescriptor

if hasattr(MambaICE.Dashboard, 'FileWriterHost') and \
        hasattr(MambaICE.Dashboard, 'FileWriterDataItem') and \
        hasattr(MambaICE.Dashboard, 'ScanDataOption') and \
        hasattr(MambaICE.Dashboard, 'UnauthorizedError'):
    from MambaICE.Dashboard import (FileWriterHost, UnauthorizedError,
                                    ScanDataOption, FileWriterDataItem)
else:
    from MambaICE.dashboard_ice import (FileWriterHost, UnauthorizedError,
                                        ScanDataOption, FileWriterDataItem)

client_verify = mamba_server.verify


class FileWriter(ABC):
    def __init__(self, filepath):
        self.path = filepath

    def add_section(self, section_name):
        pass

    def add_dataset(self, section_name, dataset_name, data_type, shape=None,
                    maxshape=None):
        pass

    def write_dataset(self, section_name, dataset_name, data_type, data):
        pass

    def append_data(self, section_name, dataset_name, data):
        pass

    def close_file(self):
        pass
    # TODO: subfile, sym link, etc


class H5FileWriter(FileWriter):
    def __init__(self, filepath):
        super().__init__(filepath)

        Path(os.path.dirname(filepath)).mkdir(parents=True, exist_ok=True)
        self.file = h5py.File(filepath, 'w-')
        self.root = self.file.create_group('scan')

        self.index = {}
        self.size = {}

    def add_section(self, section_name):
        self.root.create_group(section_name)

    def add_dataset(self, section_name, dataset_name, data_type: DataType,
                    shape=None, maxshape=None):
        path = f"{section_name}/{dataset_name}"
        self.root[section_name].create_dataset(
            dataset_name, shape, maxshape=maxshape,
            dtype=self.to_h5_type(data_type))
        self.index[path] = 0
        self.size[path] = shape[0]

    def write_dataset(self, section_name, dataset_name, data_type, data):
        path = f"{section_name}/{dataset_name}"
        np_arr = np.array(data)
        shape = np.shape(np_arr)
        dset = self.root[section_name].create_dataset(
            dataset_name, np.shape(np_arr), dtype=self.to_h5_type(data_type)
        )
        dset.write_direct(np_arr)
        if shape:
            self.index[path] = shape[0] - 1
            self.size[path] = shape[0]

    def append_data(self, section_name, dataset_name, data):
        path = f"{section_name}/{dataset_name}"
        if path in self.index:
            i = self.index[path]
            if i >= self.size[path]:
                dset = self.root[section_name][dataset_name]
                shape = list(dset.shape)
                shape[0] = i+1
                dset.resize(shape)

            self.root[section_name][dataset_name][i] = data
            self.index[path] += 1
        else:
            raise TypeError(f"{path} is not an array.")

    def close_file(self):
        self.file.close()

    @staticmethod
    def to_h5_type(_type: DataType):
        if _type == DataType.Float:
            return 'f8'
        elif _type == DataType.Integer:
            return 'i'
        elif _type == DataType.String:
            return 'U'
        elif _type == DataType.Array:
            return 'f8'


class FileSection:
    def __init__(self, section_name):
        self.section_name = section_name
        self.data_items = []


class FileWriterHostI(FileWriterHost, DataClientCallback):
    def __init__(self, writer_type, device_mgr: DeviceManagerI,
                 _dir, prefix, name_pattern):
        super().__init__()
        self.logger = mamba_server.logger
        self.writer_type = writer_type
        self.dir = _dir
        self.prefix = prefix
        self.pattern = name_pattern
        self.dev_mgr = device_mgr

        self.ongoing_scan_id = -1
        self.main_writer = None
        self.aux_writers = []

        self.env_sections = {}
        self.data_items = {}

        self.scan_data_options = {}

    def set_scan_data_options(self):
        pass

    @client_verify
    def setDirectory(self, _dir, current=None):
        self.dir = _dir

    @client_verify
    def addEnvironmentSection(self, section_name, current=None):
        self.env_sections[section_name] = FileSection(section_name)

    @client_verify
    def addEnvironmentItems(self, section_name, items: List[FileWriterDataItem],
                            current=None):
        self.env_sections[section_name].data_items.extend(items)

    @client_verify
    def removeEnvironmentItem(self, section_name, item: FileWriterDataItem,
                              current=None):
        sections = self.env_sections

        to_remove = -1
        for i, _item in enumerate(sections[section_name]):
            if _item.device_name == item.device_name and \
                    _item.data_name == item.data_name:
                to_remove = i

        if to_remove >= 0:
            del sections[section_name][to_remove]

    @client_verify
    def removeAllEnvironmentItems(self, section_name, current=None):
        self.env_sections[section_name].data_items = []

    @client_verify
    def updateScanDataOptions(self, sdos: List[ScanDataOption], current=None):
        self.scan_data_options = {sdo.name: sdo for sdo in sdos}

    def scan_start(self, _id, data_descriptors: List[DataDescriptor]):
        self.ongoing_scan_id = _id
        name = self.pattern.format(prefix=self.prefix,
                                   scan_id=_id,
                                   session=mamba_server.session_start_at)
        path = os.path.join(self.dir, name)
        self.main_writer = self.writer_type(path)
        assert isinstance(self.main_writer, FileWriter)

        self.main_writer.add_section("data")

        for key, sec in self.env_sections:
            self.main_writer.add_section(key)
        self.populate_env_items()

        self.data_items = {des.name: des for des in data_descriptors}
        for des in data_descriptors:
            if des.name in self.scan_data_options and \
                    self.scan_data_options[des.name].save:

                writer = None
                if not self.scan_data_options[des.name].single_file:
                    writer = self.main_writer
                else:
                    name = self.pattern.format(prefix=self.prefix,
                                               scan_id=_id,
                                               session=mamba_server.session_start_at)
                    path = os.path.join(self.dir, name)
                    writer = self.writer_type(path)
                    writer.add_section("data")
                    self.aux_writers[des.name] = writer

                writer.add_dataset("data",
                                   des.name,
                                   des.type,
                                   [1] + des.shape,
                                   [None] + des.shape)
                # TODO: How can I get the length of this scan?

    def scan_end(self, status):
        if self.main_writer:
            self.main_writer.close_file()
            self.main_writer = None

        if self.aux_writers:
            for writer in self.aux_writers:
                writer.close_file()
            self.aux_writers = []

        self.ongoing_scan_id = -1

    def data_update(self, frames):
        if self.ongoing_scan_id > 0:
            for frame in frames:
                self.main_writer.append_data("data", frame.name,
                                             data_frame_to_value(frame))

    def populate_env_items(self):
        for env_section in self.env_sections:
            sec_name = env_section.section_name
            for item in self.data_items:
                assert isinstance(item, FileWriterDataItem)
                sec_path = sec_name + "/" + item.device_name
                self.main_writer.add_section(sec_name + "/" + item.device_name)
                frame = self.dev_mgr.getDeviceField(item.device_name,
                                                    item.data_name)
                self.main_writer.write_dataset(sec_path,
                                               item.data_name,
                                               frame.type,
                                               data_frame_to_value(frame))


def initialize(adapter,
               device_mgr: DeviceManagerI,
               data_router: DataRouterI):
    mamba_server.file_writer_host = FileWriterHostI(
        H5FileWriter,
        device_mgr,
        mamba_server.config['files']['dir'],
        mamba_server.config['files']['prefix'],
        mamba_server.config['files']['name_pattern']
    )

    data_router.local_register_client("FileWriter",
                                      mamba_server.file_writer_host)
    data_router.local_subscribe_all("FileWriter")

    adapter.add(mamba_server.file_writer_host,
                Ice.stringToIdentity("FileWriterHost"))

    mamba_server.logger.info("FileWriterHost initialized.")
