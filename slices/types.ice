[["python:pkgdir:MambaICE"]]

module MambaICE {
    sequence<byte> bytes;
    sequence<double> doubles;
    sequence<string> strings;

    enum DataType { Float, String, Integer, Array };
    enum DeviceType { Virtual, Motor, Detector };
    sequence<int> Shape;

    struct DataDescriptor {
        string name;
        DataType type;
        Shape shape;
    };
    sequence<DataDescriptor> DataDescriptors;

    class TypedDataFrame {
        string name;
        DataType type;
        double timestamp;
    };

    sequence<TypedDataFrame> TypedDataFrames;

    class StringDataFrame extends TypedDataFrame {
        string value;
    };

    class FloatDataFrame extends TypedDataFrame {
        double value;
    };

    class IntegerDataFrame extends TypedDataFrame {
        int value;
    };

    class ArrayDataFrame extends TypedDataFrame {
        Shape shape;
        doubles data;
    };

    struct DeviceEntry {
        string name;
        DeviceType type;
        DataDescriptors configs;
        DataDescriptors readings;
    };

    sequence<DeviceEntry> DeviceEntries;
};

