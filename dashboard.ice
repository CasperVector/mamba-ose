module Dashboard {
    sequence<byte> bytes;
    sequence<string> strings;

    exception UnauthorizedError {
        string reason;
    };

    // --- Client Side ---

    interface TerminalClient {
        void stdout(bytes s);
    };

    struct DataFrame {
        string name;
        bytes value;
        double timestamp;
    };

    enum DataType { Float, String };
    sequence<int> Shape;

    struct DataDescriptor {
        string name;
        DataType type;
        Shape shape;
    };

    sequence<DataDescriptor> DataDescriptors;
    sequence<DataFrame> DataFrames;

    enum ScanExitStatus { Success, Abort, Fail };

    interface DataClient {
        void scanStart(string id, DataDescriptors keys);
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

    interface DataHost {
        void registerClient(DataClient* client) throws UnauthorizedError;
        void subscribe(strings items) throws UnauthorizedError;
        void subscribeAll() throws UnauthorizedError;
    };
};
