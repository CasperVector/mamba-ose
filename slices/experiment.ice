#include<types.ice>

[["python:pkgdir:MambaICE"]]

module MambaICE {
    module Experiment {
        exception UnknownDeviceException { };

        interface DeviceQuery {
            DeviceEntries listDevices();
            DeviceEntries getDevicesByType(string type);
            TypedDataFrames getDeviceConfigurations(string name);
            TypedDataFrames getDeviceReadings(string name);
        };
    };
};