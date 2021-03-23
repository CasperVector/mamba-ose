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

        // --- Scan ---

        struct MotorScanInstruction {
            string name;
            double start;
            double stop;
            int point_num;
        }

        sequence<MotorScanInstruction> ScanMotorInstructionSet;

        struct ScanInstruction {
            ScanMotorInstructionSet motors;
            strings detectors;
        }

        interface ScanManager {
            ScanInstruction getScanPlan(string name);
            strings listScanPlans();
            void setScanPlan(string name, ScanInstruction instruction);
            void runScan(string plan_name);
            void terminateScan();
            void resumeScan();
            void pauseScan();
        };
    };
};
