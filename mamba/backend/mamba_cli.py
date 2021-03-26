#!/usr/bin/python3

import os
import sys
import yaml

def main():
    config = sys.argv[1] if len(sys.argv) > 1 \
        else os.path.expanduser("~/.mamba/config.yaml")
    with open(config, "r") as f:
        config = yaml.safe_load(f)["backend"]
    os.execlp("python3", "python3", "-m",
        "mamba.backend.zspawn", str(config["lport"]),
        "ipython3", "--InteractiveShellApp.exec_files=%r" %
            [os.path.expanduser(config["init"])])

if __name__ == "__main__":
    main()

