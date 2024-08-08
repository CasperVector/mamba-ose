#!/usr/bin/python3

import subprocess
from logging import error, warn
from setuptools import setup, find_packages
import platform


# TODO: remove this until python-ldap solve this
try:
    import ldap
except ImportError as e:
    if platform.system().lower() == 'windows':
        error("""
On windows, you will encounter compilation failure for python-ldap,
please download corresponding python wheels (https://github.com/cgohlke/python-ldap-build/releases/tag/v3.4.4),
then `pip install <your python_ldap-*.whl>`.\n""")
        raise e
try:
    import PyQt5
    qrc_cmd = "pyrcc5"
    uic_cmd = "pyuic5"
except ImportError:
    error("pyqt5 not found, need pyrcc5\n")
    try:
        import PySide6
        qrc_cmd = "pyside6-rcc"
        uic_cmd = "pyside6-uic"
    except ImportError:
        error("pyside6 not found, need pyside6-rcc\n")

try:

    qrc_file = "mamba/icons/rc_icons.qrc"
    qrc_py_file = "mamba/icons/rc_icons.py"
    ui_file_1 = "mamba/gengyd/widgets/ui_motorwidget.ui"
    ui_file_2 = "mamba/gengyd/widgets/ui_scanmechanismwidget.ui"
    ui_file_1_py = "mamba/gengyd/widgets/ui_motorwidget.py"
    ui_file_2_py = "mamba/gengyd/widgets/ui_scanmechanismwidget.py"
    subprocess.check_call([qrc_cmd, "-o", qrc_py_file, qrc_file])
    subprocess.check_call([uic_cmd, "-o", ui_file_1_py, ui_file_1])
    subprocess.check_call([uic_cmd, "-o", ui_file_2_py, ui_file_2])
except:
    error(f"pyqt resouces compilation failed.\n")
    exit(-1)

with open("requirements.txt") as reqs:
    requirements = reqs.readlines()

setup(
    name="mamba",
    version="0.1a1",
    packages=find_packages(),
    author="Yanda Geng, Yu Liu",
    author_email="gengyanda16@smail.nju.edu.cn, liuyu91@ihep.ac.cn",
    description="Interactive experiment control toolkit for HEPS",
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License"
        " v2 or later (LGPLv2+)",
    ],
    entry_points={
        "console_scripts": [
            "zspawn=mamba.backend.zspawn:main",
            "mamba-cli=mamba.backend.mamba_cli:main",
            "mamba-gui=mamba.frontend.mamba_gui:main",
        ]
    },
    package_data={"mamba.frontend.widgets.ui": ["*.ui", "*.qrc", "icons/*.png"]},
)
