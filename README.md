# Mamba

_Mamba_ is the experimental control framework-to-be of HEPS. It aims to provide

-  A GUI frontend (client) on users' PC, with a variety of widgets available to 
    1. Design experiment patterns (scan routine),
    2. Control the parameters of all devices of a beamline,
    3. Run experiments,
    4. Visualize the experiment data in real time,
    5. Interact with the data analysis system of the HEPS central computational cluster,
    6. And more...
-  All of these are supported by a backend (server) running on the _beamline control server_, which consists of multiple service providers and the _bluesky_ experiment control software embedded inside a IPython shell.

Mamba' versatile GUI gathers everything one experimentalist need to run an experiment, meanwhile offer flexibilities for him to customize the interface and components he uses.

Clients and servers talk through ICE, a RPC framework. The separation of client and the server increases the robustness of the entire system, naturally offers ways for multiple clients cooperating at the same time.

Mamba is powered by a series of open source projects: PyQt, scipy environment, ICE, termqt.

## Get Started

### Server Side

1. Clone this repo

   ```bash
   git clone http://heps-se.ihep.ac.cn/gengyd/mamba.git
   cd mamba
   python -m venv venv # Create a new virtual environment
   ```

2. Activate the `venv` just created. On Linux:
   ```bash
   ./venv/bin/activate
   ```
   On Windows:
   ```bash
   .\venv\Scripts\activate
   ```
   

3. bluesky need to be installed first. See [bluesky's tutorial](https://blueskyproject.io/bluesky/tutorial.html) (remember to install everything with `venv/bin/python3 -m pip`).

4. Install ICE

   ```
   python -m pip install zeroc-ice
   ```

5. Install termqt

   ```bash
   git clone https://github.com/TerryGeng/termqt
   (cd termqt && python setup.py install)
   ```

6. Install mamba

    ```bash
    python setup.py develop
    ```

7. Run the server

   ```
   mamba_host
   ```

   

### Client Side

1. Clone this repo

   ```bash
   git clone http://heps-se.ihep.ac.cn/gengyd/mamba.git
   cd mamba
   ```
   
2. Activate the `venv` just created. See above.

3. Install pyqt5 and ICE

   ```bash
   python -m pip install pyqt5 zeroc-ice
   ```

4. Install termqt

   ```bash
   git clone https://github.com/TerryGeng/termqt
   (cd termqt && python setup.py develop)
   ```

5. Install mamba

    ```bash
    python setup.py develop
    ```

6. Make a copy of `mamba_client/client_config.yaml`, correctly set the IP address of the server inside your copy:

   ```yaml
   ---
   network:
     host_address: 127.0.0.1 # <--- edit this line
   ```

6. Run the client

   ```
   mamba_client -c {the path to your copy of client_config.yaml}
   ```

   


## TODO List

- [x] Ice session management (https://doc.zeroc.com/technical-articles/general-topics/design-patterns-for-secure-ice-applications)
- [x] Ice configuration file, avoid hardcoded port number in the program
- [x] Ice interface
- [x] IPython prompt enhancement (https://github.com/ipython/ipython/pull/10500/files, https://ipython.readthedocs.io/en/stable/config/details.html#custom-prompts)
- [x] termqt: bug fixes and allow customized escape sequence
- [x] Bluesky data callback
- [x] Slice interface refactored - _2020.9.13_
- [x] DeviceQuery interface, handle device config query request - _2020.9.13_
- [x] Server: DeviceManager - _2020.9.14_
  - [x] cache device descriptions - _2020.9.14_
  - [x] relay config query request - _2020.9.14_
  - [x] set config value interface - _2020.9.14_
  - [ ] periodically push reading back? (DataRouter?)
- [x] Client: DeviceConfigDialog - _2020.9.14_
- [ ] ~~Motor control panel~~
- [x] DataType.Array - _2020.9.24_
- [x] Server: File storing mechanism - _2020.9.25_
  - [x] Scan metadata storage
  - [x] AreaDetector save into files
  - [x] Debug - _2020.9.26_
- [ ] Client: Environment data selection dialog
- [x] Client: Scan mechanics design widget - _2020.9.22_
  - [x] Experiment control navbar (pause, continue, halt)
  - [x] Save plan (server side) - _2020.9.25_
  - [x] Save plan UI
  - [x] Scan status - _2020.9.26_
  - [x] Scan control - _2020.9.26_
  - [ ] File Options
- [ ] Client: 2D visualization
- [ ] Client: plot widgets improvement
  - [ ] draw multiple lines on the same plot
  - [ ] customizable x-axis
- [ ] Terminal buffer on server-side
- [x] Server: Lost connection management - _2020.9.26_
- [x] Subprocess logging mechanism
- [ ] Documentation
