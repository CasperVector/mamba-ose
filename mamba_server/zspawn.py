#!/usr/bin/python3

import errno
import os
import pexpect
import tty
import zmq

class zspawn(pexpect.pty_spawn.spawn):

    def __init__(self, port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sock = zmq.Context().socket(zmq.REP)
        self.sock.bind("tcp://127.0.0.1:%d" % port)
        self.poller = zmq.Poller()
        for fd in [self.child_fd, self.STDIN_FILENO, self.sock]:
            self.poller.register(fd, zmq.POLLIN)
        self.interact()

    # zmq/error.py says EINTR should be caught internally in pyzmq.
    def _poll(self):
        return [afd for afd, _ in self.poller.poll()]

    # Class-private methods (self.__method) are not inherited, hence the dup.
    def interact(self):
        self.write_to_stdout(self.buffer)
        self.stdout.flush()
        self._buffer = self.buffer_type()
        mode = tty.tcgetattr(self.STDIN_FILENO)
        tty.setraw(self.STDIN_FILENO)
        try:
            self._interact_copy()
        finally:
            tty.tcsetattr(self.STDIN_FILENO, tty.TCSAFLUSH, mode)

    # Also a duplicate here.
    def _interact_writen(self, fd, data):
        while data != b'' and self.isalive():
            n = os.write(fd, data)
            data = data[n:]

    def _interact_read(self, fd):
        return fd.recv() if fd == self.sock else os.read(fd, 1000)

    def _interact_copy(self):
        while self.isalive():
            r = self._poll()
            if self.child_fd in r:
                try:
                    data = self._interact_read(self.child_fd)
                except OSError as err:
                    if err.args[0] == errno.EIO:
                        break
                    raise
                if data == b"":
                    break
                self._log(data, "read")
                os.write(self.STDOUT_FILENO, data)
            for fd in [self.STDIN_FILENO, self.sock]:
                if fd in r:
                    data = self._interact_read(fd)
                    self._log(data, "send")
                    self._interact_writen(self.child_fd, data)
                    if fd == self.sock:
                        fd.send(b"")

def main():
    import sys
    zspawn(int(sys.argv[1]), sys.argv[2], sys.argv[3:])

if __name__ == "__main__":
    main()

