#!/usr/bin/python3

def init():
    from IPython import get_ipython
    from .mzserver import config_read
    if not get_ipython():
        return main()
    config = config_read()
    config.server_init(globals(), config)

def main():
    import os, sys
    from .mzserver import config_read
    os.execlp(
        "python3",
        "python3", "-m", "mamba.backend.zspawn", "%d" % config_read().lport,
        "ipython3", "-i", "-m", "mamba.backend.mamba_cli", *sys.argv[1:]
    )

if __name__ == "__main__":
    init()
    del init, main

