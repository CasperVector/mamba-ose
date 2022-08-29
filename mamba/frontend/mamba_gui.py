#!/usr/bin/python3

import importlib
import re
from ..backend.mzserver import config_read

def guis_find(paths):
    ret = []
    for mod, farg, desc in [path.split(":") for path in paths]:
        f, arg = re.match(r"([^()]+)\(([^()]*)\)$", farg).groups()
        ret.append((mod, f, arg, desc))
    return ret

def gui_exec(mod, f, arg):
    getattr(importlib.import_module(mod), f)(arg)

def main():
    guis = guis_find(config_read()["frontend"]["guis"])
    if not guis:
        raise ValueError("No GUI listed in Mamba config file")
    if len(guis) == 1:
        i = 0
    else:
        for i, (mod, f, arg, desc) in enumerate(guis):
            print("%d: %s" % (i, desc))
        i = int(input("GUI to run [0]: ") or "0")
    mod, f, arg, desc = guis[i]
    gui_exec(mod, f, arg)

if __name__ == "__main__":
    main()

