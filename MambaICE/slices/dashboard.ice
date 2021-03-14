#include<types.ice>

[["python:pkgdir:MambaICE"]]

module MambaICE {
    module Dashboard {
        exception UnknownDeviceException { };
        enum ScanExitStatus { Success, Abort, Fail };

        interface DataClient {
            void scanStart(int id, DataDescriptors keys);
            void dataUpdate(TypedDataFrames data);
            void scanEnd(ScanExitStatus status);
        };

        // --- Server Side ---

        interface SessionManager {
            void login();
            void logout();
        };

        interface DataRouter {
            void registerClient(DataClient* client);
            void subscribe(strings items);
            void subscribeAll();
            void unsubscribe(strings items);
        };

        interface DataRouterRecv {
            void scanStart(int id, DataDescriptors keys);
            void pushData(TypedDataFrames frames);
            void scanEnd(ScanExitStatus status);
        };

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

        struct FileWriterDataItem {
            string device_name;
            string data_name;
        };

        sequence<FileWriterDataItem> FileWriterDataItems;

        struct ScanDataOption {
            string dev;
            string name;
            bool save;
            bool single_file;
        };

        sequence<ScanDataOption> ScanDataOptions;

        interface FileWriterHost {
            void setDirectory(string dir);
            // void setFileNamePattern
            void addEnvironmentSection(string section_name);
            void addEnvironmentItems(string section_name, FileWriterDataItems items);
            void removeEnvironmentItem(string section_name, FileWriterDataItem item);
            void removeAllEnvironmentItems(string section_name);
            void updateScanDataOptions(ScanDataOptions sdos);
        }

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
