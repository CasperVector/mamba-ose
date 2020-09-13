[["python:pkgdir:MambaICE"]]

module MambaICE {
    sequence<byte> bytes;
    sequence<string> strings;

    enum DataType { Float, String, Integer, Array };
    enum DeviceType { Motor, Detector };
    sequence<int> Shape;

    struct DataDescriptor {
        string name;
        DataType type;
        Shape shape;
    };
    dictionary<string, DataDescriptor> DataDescriptors;

    struct DataFrame {
        string name;
        bytes value;
        double timestamp;
    };
    sequence<DataFrame> DataFrames;

    struct TypedDataFrame {
        string name;
        DataType type;
        Shape shape;
        bytes value;
        double timestamp;
    }
    sequence<TypedDataFrame> TypedDataFrames;

    struct DeviceEntry {
        string name;
        DeviceType type;
        DataDescriptors configs;
        DataDescriptors readings;
    };

    sequence<DeviceEntry> DeviceEntries;
};

