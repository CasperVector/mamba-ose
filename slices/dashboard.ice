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
            void dataUpdate(DataFrames data);
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

            // --- method for the data producer ---
            void scanStart(int id, DataDescriptors keys) throws UnauthorizedError;
            void pushData(DataFrames frames) throws UnauthorizedError;
            void scanEnd(ScanExitStatus status) throws UnauthorizedError;
        };

        interface DeviceManager {
            DeviceEntries listDevices();
            strings getDevicesByType(string type);
            TypedDataFrames getDeviceConfigurations(string name);
            TypedDataFrames getDeviceReadings(string name);

            // --- method for experiment subprocess ---
            void addDevices(DeviceEntries entries);
        };
    };
};
