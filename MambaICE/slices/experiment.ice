#include<types.ice>

[["python:pkgdir:MambaICE"]]

module MambaICE {
    module Experiment {
        exception UnknownDeviceException { };

        interface DeviceQuery {
            DeviceEntries listDevices();
            TypedDataFrames getDeviceConfigurations(string name);
            TypedDataFrames getDeviceReadings(string name);
            DataDescriptors describeDeviceReadings(string name);
            TypedDataFrame getDeviceFieldValue(string dev_name, string field_name);
        };

        interface ScanController {
            void pause();
            void abort();
            void halt();
        };
    };
};