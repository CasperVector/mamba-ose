#!/usr/bin/python3

import os
import sys
from .mzserver import config_read

def main():
    config = config_read(sys.argv[1] if len(sys.argv) > 1 else "")["backend"]
    os.execlp("python3", "python3", "-m",
        "mamba.backend.zspawn", str(config["lport"]),
        "ipython3", "--InteractiveShellApp.exec_files=%r" %
            [os.path.expanduser(config["init"])])

if __name__ == "__main__":
    main()

