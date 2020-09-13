# Modules running in pty thread

This folder holds all modules that is running in the IPython
subprocess.

They can't directly invoke functions from the main server thread.

In order to interactive with IPython terminal without jamming the
main server thread and utilizing the wonderful IPython terminal
features like colored output, auto-completion, etc., it is a must
to run IPython thread in an independent pty subprocess that is
forked from the main server process.

For more information, see
- https://dev.to/napicella/linux-terminals-tty-pty-and-shell-192e
- https://linux.die.net/man/7/pty

All experiment related components are loaded directed in the
IPython subprocess, including bluesky and all ophyd and device
wrappers. These components are not inside the main server process,
hence can only be controlled by IPython thread.

This designed is intended, in order to guarantee that all
experiment-related operations are actually displayed in IPython
terminal as python code and recorded in the history.

The communication between the IPython subprocess consists of two
parts: one is the stdin and stdout pipe given by pty, the other
is RPC connection.

The pipe is used for forwarding all terminal input and output to/
from IPython terminal, while RPC is used for receiving data,
or acquiring information from devices. Don't operate devices
through PRC because it is not recorded in the IPython terminal.
