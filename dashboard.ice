module Dashboard {
    sequence<byte> bytes;

    exception UnauthorizedError {
        string reason;
    };

    // --- Client Side ---

    interface TerminalClient {
        void stdout(bytes s);
    };

    interface DataClient{
        void dataUpdate(string id, string json);
        void clear();
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
        void subscribe(string item_name) throws UnauthorizedError;
        void subscribeAll() throws UnauthorizedError;
    };
};
