## Mamba

Mamba is the experimental control framework-to-be of HEPS. It aims to provide

* A GUI frontend with a variety of widgets available to (but not limited to)
  - Control the parameters of devices on the beamline;
  - Design experiment patterns and run experiments routines;
  - Do data analysis and visualisation, online or off-line, using HPC or not.

* All of these are supported by a backend running inside an IPython shell,
  and communicates with the frontend using ZeroMQ; the backend is the part
  of Mamba which actually interacts with the Bluesky objects inside the shell.

* Both the frontend and the backend run on the Linux-based beamline-control
  server, and both are Python 3 only; the xpra GUI forwarding system allows
  for comfortable remote access from popular operating systems.

## Usage

* Building and (optionally) installation:
    ```sh
    $ pip3 install -r requirements.txt
    $ ./prepare.sh
    $ python3 ./setup.py install  # For real installation; maybe with `--user`.
    ```

* Before first use (customise the config after this):
    ```sh
    $ mkdir -p mamba_site  # For real installation, use ~/mamba_site.
    $ cp docs/config_gengyd.py mamba_site/config.py
    $ cp docs/init_sim.py mamba_site/init.py
    ```

* Routine use, starting the backend first:
    ```sh
    $ cd ~ && mamba-cli  # After real installation; otherwise see below.
    $ cd /path/to/mamba && python3 -m mamba.backend.mamba_cli
    ```

* Routine use, starting the frontend in another terminal:
    ```sh
    $ cd ~ && mamba-gui  # After real installation; otherwise see below.
    $ cd /path/to/mamba && python3 -m mamba.frontend.mamba_gui
    ```

