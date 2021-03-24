#include<types.ice>

[["python:pkgdir:MambaICE"]]

module MambaICE {
    module Dashboard {
        exception UnknownDeviceException { };

        // --- Server Side ---

        interface DeviceManager {
            DeviceEntries listDevices();
            TypedDataFrames getDeviceConfigurations(string name);
            TypedDataFrames getDeviceReadings(string name);
            DataDescriptors describeDeviceReadings(string name);
            TypedDataFrame getDeviceField(string dev_name, string field_name);

            void setDeviceConfiguration(string name, TypedDataFrame frame);
            void setDeviceValue(string name, TypedDataFrame frame);
            void addDevices(DeviceEntries entries);
        };
    };
};
