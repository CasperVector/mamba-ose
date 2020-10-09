from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.sdist import sdist


def compile_slices():
    import os, Ice, IcePy
    print("=== Compiling ICE slices...")
    slice_dir = Ice.getSliceDir()
    root = os.path.dirname(__file__)
    mamba_slice_dir = os.path.join(root, "MambaICE/slices/")
    argv = ['slice2py']
    if slice_dir:
        argv.append("-I" + slice_dir)
    argv += f"--underscore --output-dir {root} -I{mamba_slice_dir}".split(" ")

    for ice in filter(lambda s: s.endswith('.ice'),
                      [f for f in os.listdir(mamba_slice_dir)]):
        print(f"Discovered {ice} ...")
        argv.append(os.path.join(mamba_slice_dir, ice))

    print("Executing slice2py with arguments: " + " ".join(argv))

    assert IcePy.compile(argv) == 0, "Failed to compiled ICE slices."


def compile_qt_ui_files():
    import os, sys
    import PyQt5.uic

    print("=== Compiling Qt's .ui files...")

    ui_dir = os.path.join(os.path.dirname(__file__), "mamba_client/widgets/ui")

    for ui in filter(lambda s: s.endswith('.ui'),
                     [f for f in os.listdir(ui_dir)]):
        ui = os.path.join(ui_dir, ui)
        print(f"Compiling {ui} ...")
        output = os.path.join(ui[:-3] + ".py")
        with open(output, "w") as f:
            PyQt5.uic.compileUi(ui, f)

    print("=== Compiling Qt's .qrc files...")
    pyrcc_candidates = [
        "pyrcc5",
        os.path.join(os.path.dirname(sys.executable), "pyrcc5"),
        os.path.join(os.path.dirname(sys.executable), "pyrcc5.exe")
    ]
    pyrcc = ""

    for qrc in filter(lambda s: s.endswith('.qrc'),
                     [f for f in os.listdir(ui_dir)]):
        qrc = os.path.join(ui_dir, qrc)
        print(f"Compiling {qrc} ...")
        output = os.path.join(qrc[:-4] + ".py")

        if not pyrcc:
            for cand in pyrcc_candidates:
                if os.system(f"{cand} {qrc} -o {output}") == 0:
                    pyrcc = cand
                    break
            if not pyrcc:
                raise FileNotFoundError("No available pyrcc5 found, or compile failed.")
        else:
            os.system(f"{pyrcc} {qrc} -o {output}")


class custom_install(install):
    def run(self):
        install.run(self)

        self.execute(compile_slices, [], msg="Compile ICE slice files")
        self.execute(compile_qt_ui_files, [], msg="Compile Qt's ui and qrc files")


class custom_develop(develop):
    def run(self):
        develop.run(self)

        self.execute(compile_slices, [], msg="Compile ICE slice files")
        self.execute(compile_qt_ui_files, [], msg="Compile Qt's ui and qrc files")


class custom_sdist(sdist):
    def make_release_tree(self, basedir, files):
        sdist.make_release_tree(self, basedir, files)
        self.execute(compile_slices, [], msg="Compile ICE slice files")
        self.execute(compile_qt_ui_files, [], msg="Compile Qt's ui and qrc files")


with open("requirements.txt") as reqs:
    requirements = reqs.readlines()

setup(
    name="mamba",
    version="0.1a1",
    packages=find_packages(exclude=("user_scripts*",)),
    author="Yanda Geng",
    author_email="gengyanda16@smail.nju.edu.cn",
    description="Interactive experiment control toolkit for HEPS.",
    keywords="experiment control gui",
    platform="any",
    install_requires=requirements,
    classifiers=[
        "License :: OSI Approved :: GNU Lesser General Public License v2 "
        "or later (LGPLv2+)",
    ],
    entry_points={
        'console_scripts': [
            'mamba_client=mamba_client.client_start:main',
            'mamba_host=mamba_server.server_start:main',
        ]
    },
    package_data={
        'MambaICE': ["slices/*.ice"],
        'mamba_client': ["widgets/ui/*.ui", "widgets/ui/*.qrc", "widgets/ui/icons/*.png", "*.yaml"],
        'mamba_server': ["*.yaml"]
    },
    cmdclass={'install': custom_install, 'develop': custom_develop, 'sdist': custom_sdist}
)

