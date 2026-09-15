#!/usr/bin/python3

import importlib
from ..backend.mzserver import config_read

def main():
    guis = config_read().guis
    if not guis:
        raise ValueError("No GUI listed in Mamba config file")
    if len(guis) == 1:
        i = 0
    else:
        for i, (mod, args, desc) in enumerate(guis):
            print("%d: %s" % (i, desc))
        i = int(input("GUI to run [0]: ") or "0")
    mod, args, desc = guis[i]
    importlib.import_module(mod).main(*args)

if __name__ == "__main__":
    main()

