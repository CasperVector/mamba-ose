import numpy as np
import json
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


def to_data_frame(name, _type: str, value, timestamp):
    _type = _type.lower()
    if _type == 'number':
        return FloatDataFrame(
            name=name,
            type=DataType.Float,
            timestamp=timestamp,
            value=float(value)
        )
    elif _type == 'integer':
        return IntegerDataFrame(
            name=name,
            type=DataType.Integer,
            timestamp=timestamp,
            value=int(value)
        )
    elif _type == 'string':
        return StringDataFrame(
            name=name,
            type=DataType.String,
            timestamp=timestamp,
            value=str(value)
        )
    elif _type == 'array':
        return to_array_data_frame(name, value, timestamp)
    assert False, f"Unknown data type {_type}"


def to_array_data_frame(name, array, timestamp):
    if isinstance(array, str):
        array = json.loads(array)

    np_array = np.array(array)
    shape = np.shape(np_array)
    packed_array = np_array.flatten()
    return ArrayDataFrame(
        name=name,
        shape=shape,
        timestamp=timestamp,
        data=packed_array
    )


def data_frame_to_value(data_frame):
    if data_frame.type == DataType.String:
        return str(data_frame.value)
    elif data_frame.type == DataType.Integer:
        return int(data_frame.value)
    elif data_frame.type == DataType.Float:
        return float(data_frame.value)
    elif data_frame.type == DataType.Array:
        return np.array(data_frame.data).reshape(data_frame.shape)


def data_frame_to_descriptor(data_frame):
    shape = []
    if data_frame.type == DataType.Array:
        shape = data_frame.shape

    return DataDescriptor(
        name=data_frame.name,
        type=data_frame.type,
        shape=shape
    )
