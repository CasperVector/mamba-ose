from typing import List
from utils.data_utils import (to_data_frame, data_frame_to_value,
                              TypedDataFrame)


class VirtualDevice(dict):
    def __init__(self, params: List[TypedDataFrame]):
        super().__init__({f.name: f for f in params})
