#!/usr/bin/python3

import os
import sys
from .mzserver import config_read

def main():
    config = config_read()["backend"]
    args = ["--"] + sys.argv[1:] if len(sys.argv) > 1 else []
    os.execlp("python3", "python3", "-m",
        "mamba.backend.zspawn", str(config["lport"]),
        "ipython3", "-i", os.path.expanduser(config["init"]), *args)

if __name__ == "__main__":
    main()

