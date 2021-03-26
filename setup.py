#!/usr/bin/python3

from setuptools import setup, find_packages

with open("requirements.txt") as reqs:
    requirements = reqs.readlines()

setup(
    name="mamba",
    version="0.1a1",
    packages=find_packages(),
    author="Yanda Geng",
    author_email="gengyanda16@smail.nju.edu.cn",
    description="Interactive experiment control toolkit for HEPS",
    keywords="experiment control gui",
    platform="any",
    install_requires=requirements,
    classifiers=[
        "License :: OSI Approved :: GNU Lesser General Public License v2 "
        "or later (LGPLv2+)",
    ],
    entry_points={
        "console_scripts": ["zspawn=mamba_server.zspawn:main",
            "mamba_client=mamba_client.client_start:main"]
    },
    package_data={
        'mamba_client':
            ["widgets/ui/*.ui", "widgets/ui/*.qrc", "widgets/ui/icons/*.png"]
    }
)

