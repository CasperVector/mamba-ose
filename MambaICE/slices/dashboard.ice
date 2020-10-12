#include<types.ice>

[["python:pkgdir:MambaICE"]]

module MambaICE {
    module Dashboard {
        exception UnauthorizedError {
            string reason;
        };

        enum ScanExitStatus { Success, Abort, Fail };

        // --- Client Side ---
        interface TerminalClient {
            void stdout(bytes s);
        };

        interface DataClient {
            void scanStart(int id, DataDescriptors keys);
            void dataUpdate(TypedDataFrames data);
            void scanEnd(ScanExitStatus status);
        };

        // --- Server Side ---

        interface SessionManager {
            void login(string username, string password) throws UnauthorizedError;
            void logout();
        };

        interface TerminalHost {
            void emitCommand(string cmd) throws UnauthorizedError;
            void registerClient(TerminalClient* client) throws UnauthorizedError;

            void stdin(bytes s) throws UnauthorizedError;
            void resize(int rows, int cols) throws UnauthorizedError;
        };

        // Handling the event emitted by underlying IPython shell and bluesky.
        interface TerminalEventHandler {
            void attach(string token);
            void enterExecution(string cmd);
            void leaveExecution(string result);
        };

        interface DataRouter {
            void registerClient(DataClient* client) throws UnauthorizedError;
            void subscribe(strings items) throws UnauthorizedError;
            void subscribeAll() throws UnauthorizedError;
            void unsubscribe(strings items) throws UnauthorizedError;

            // --- method for the data producer ---
            void scanStart(int id, DataDescriptors keys) throws UnauthorizedError;
            void pushData(TypedDataFrames frames) throws UnauthorizedError;
            void scanEnd(ScanExitStatus status) throws UnauthorizedError;
        };

        interface DeviceManager {
            DeviceEntries listDevices();
            strings getDevicesByType(string type);
            TypedDataFrames getDeviceConfigurations(string name);
            TypedDataFrames getDeviceHintedReadings(string name);
            TypedDataFrames getDeviceReadings(string name);
            TypedDataFrame getDeviceField(string dev_name, string field_name);

            void setDeviceConfiguration(string name, TypedDataFrame frame);
            void setDeviceValue(string name, TypedDataFrame frame);

            void addVirtualDevice(string name, TypedDataFrames frames);

            // --- method for experiment subprocess ---
            void addDevices(DeviceEntries entries);
        };

        struct FileWriterDataItem {
            string device_name;
            string data_name;
        }

        sequence<FileWriterDataItem> FileWriterDataItems;

        interface FileWriterHost {
            void setDirectory(string dir);
            // void setFileNamePattern
            void addEnvironmentSection(string section_name);
            void addEnvironmentItems(string section_name, FileWriterDataItems items);
            void removeEnvironmentItem(string section_name, FileWriterDataItem item);
            void removeAllEnvironmentItems(string section_name);
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
