import numpy as np
import json
import time
from typing import Iterable
import MambaICE

if hasattr(MambaICE, 'TypedDataFrame') and hasattr(MambaICE, 'DataType') and \
        hasattr(MambaICE, 'StringDataFrame') and \
        hasattr(MambaICE, 'IntegerDataFrame') and \
        hasattr(MambaICE, 'FloatDataFrame') and \
        hasattr(MambaICE, 'ArrayDataFrame') and \
        hasattr(MambaICE, 'DataDescriptor'):
    from MambaICE import (DataType, TypedDataFrame, FloatDataFrame,
                          IntegerDataFrame, StringDataFrame, ArrayDataFrame,
                          DataDescriptor)
else:
    from MambaICE.types_ice import (DataType, TypedDataFrame, FloatDataFrame,
                                    IntegerDataFrame, StringDataFrame,
                                    ArrayDataFrame, DataDescriptor)


def string_to_type(string):
    string = string.lower()
    if string == 'number':
        return DataType.Float
    elif string == 'string':
        return DataType.String
    elif string == 'integer':
        return DataType.Integer
    elif string == 'array':
        return DataType.Array


def to_data_frame(name, _type: DataType, value, timestamp=None):
    if not timestamp:
        timestamp = time.time()

    if _type == DataType.Float:
        return FloatDataFrame(
            name=name,
            type=DataType.Float,
            timestamp=timestamp,
            value=float(value)
        )
    elif _type == DataType.Integer:
        return IntegerDataFrame(
            name=name,
            type=DataType.Integer,
            timestamp=timestamp,
            value=int(value)
        )
    elif _type == DataType.String:
        return StringDataFrame(
            name=name,
            type=DataType.String,
            timestamp=timestamp,
            value=str(value)
        )
    else:
        assert _type == DataType.Array, f"Wrong Type {_type}"
        return to_array_data_frame(name, value, timestamp)


def to_array_data_frame(name, array, timestamp):
    if isinstance(array, str):
        array = json.loads(array)

    np_array = np.array(array)
    shape = np.shape(np_array)
    packed_array = np_array.flatten()
    return ArrayDataFrame(
        name=name,
        type=DataType.Array,
        shape=shape,
        timestamp=timestamp,
        value=packed_array
    )


def data_frame_to_value(data_frame):
    if data_frame.type == DataType.String:
        return str(data_frame.value)
    elif data_frame.type == DataType.Integer:
        return int(data_frame.value)
    elif data_frame.type == DataType.Float:
        return float(data_frame.value)
    elif data_frame.type == DataType.Array:
        return np.array(data_frame.value).reshape(data_frame.shape)


def data_frame_to_descriptor(data_frame):
    shape = []
    if data_frame.type == DataType.Array:
        shape = data_frame.shape

    return DataDescriptor(
        name=data_frame.name,
        type=data_frame.type,
        shape=shape
    )
