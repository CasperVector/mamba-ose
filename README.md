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

Mamba is powered by a series of open source projects: PyQt, scipy environment, ICE, pyqterm.

## Get Started

### Server Side

1. Clone this repo

      ```bash
   git clone http://heps-se.ihep.ac.cn/gengyd/mamba.git
   cd mamba
   python -m venv venv # Create a new virtual environment
      ```

2. bluesky need to be installed first. See [bluesky's tutorial](https://blueskyproject.io/bluesky/tutorial.html) (remember to install everything with `venv/bin/python3 -m pip`).

3. Install ICE

   ```
   venv/bin/python3 -m pip install zeroc-ice
   ```

4. Install pyqterm

      ```bash
   git clone https://github.com/TerryGeng/pyqterm
   (cd pyqterm && ../venv/bin/python setup.py develop)
      ```

5. Run the server

   ```
   venv/bin/python3 server_start.py
   ```

   

### Client Side

1. Clone this repo

   ```bash
   git clone http://heps-se.ihep.ac.cn/gengyd/mamba.git
   cd mamba
   ```

2. Install pyqt5 and ICE

   ```bash
   venv/bin/python3 -m pip install pyqt5 zeroc-ice
   ```

3. Install pyqterm

   ```bash
   git clone https://github.com/TerryGeng/pyqterm
   (cd pyqterm && ../venv/bin/python setup.py develop)
   ```

4. Compile ICE's Slice interface description into python code

   ```bash
   venv/bin/slice2py dashboard.ice
   ```

5. Correctly set the IP address of the server inside `client_config.yaml`:

   ```yaml
   ---
   network:
     host_address: 127.0.0.1 # <--- edit this line
     host_port: 10076
     protocol: tcp
   
   ```

6. Run the client

   ```
   venv/bin/python3 client_start.py
   ```

   


## TODO List

- [x] Ice session management (https://doc.zeroc.com/technical-articles/general-topics/design-patterns-for-secure-ice-applications)
- [x] Ice configuration file, avoid hardcoded port number in the program
- [x] Ice interface
- [x] IPython prompt enhancement (https://github.com/ipython/ipython/pull/10500/files, https://ipython.readthedocs.io/en/stable/config/details.html#custom-prompts)
- [x] pyqterm: bug fixes and allow customized escape sequence
- [x] Bluesky data callback
- [ ] Client: plot widgets improvement
  - [ ] draw multiple lines on the same plot
  - [ ] customizable x-axis
- [ ] Motor control panel
  - [ ] Server: EPICS host? ophyd?
  - [ ] Client: motor control panel widget
- [ ] Experiment control navbar (pause, continue, halt)
