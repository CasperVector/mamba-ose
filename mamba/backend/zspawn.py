#!/usr/bin/python3

import errno
import os
import pexpect
import tty
import zmq

class zspawn(pexpect.pty_spawn.spawn):

    def __init__(self, port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        os.set_blocking(self.child_fd, False)
        self.backlog = [b"", None]
        self.sock = zmq.Context().socket(zmq.REP)
        self.sock.bind("tcp://127.0.0.1:%d" % port)
        self.pollers = zmq.Poller(), zmq.Poller()
        for fd in [self.child_fd, self.STDIN_FILENO, self.sock]:
            self.pollers[0].register(fd, zmq.POLLIN)
        self.pollers[1].register(self.child_fd, zmq.POLLIN | zmq.POLLOUT)
        self.interact()

    # zmq/error.py says EINTR should be caught internally in pyzmq.
    def _poll(self, poller):
        return dict(poller.poll())

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

    def _interact_writen(self, fd, backlog):
        n = os.write(fd, backlog[0][:1000])
        backlog[0] = backlog[0][n:]

    def _interact_read(self, fd):
        return fd.recv() if fd == self.sock else os.read(fd, 1000)

    def _interact_copy(self):
        while self.isalive():
            r = self._poll(self.pollers[bool(self.backlog[0])])
            if r.get(self.child_fd, 0) & zmq.POLLIN:
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
            if r.get(self.child_fd, 0) & zmq.POLLOUT:
                if self.isalive():
                    self._interact_writen(self.child_fd, self.backlog)
                    if self.backlog == [b"", self.sock]:
                        self.sock.send(b"")
            else:
                for fd in [self.STDIN_FILENO, self.sock]:
                    if fd in r:
                        self.backlog = [self._interact_read(fd), fd]
                        self._log(self.backlog[0], "send")
                        break

def main():
    import sys
    zspawn(int(sys.argv[1]), sys.argv[2], sys.argv[3:])

if __name__ == "__main__":
    main()

