#!/usr/bin/python3

from setuptools import setup, find_packages

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
        " v2 or later (LGPLv2+)"
    ],
    entry_points={
        "console_scripts": ["zspawn=mamba.backend.zspawn:main",
             "mamba-cli=mamba.backend.mamba_cli:main",
             "mamba-gui=mamba.frontend.mamba_gui:main"]
    },
    package_data={
        "mamba.gengyd.widgets": ["*.ui"],
        "mamba": ["icons/*.png", "icons/*.qrc"]
    }
)

