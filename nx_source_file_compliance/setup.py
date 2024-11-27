## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
import setuptools


pkg_vars = {}
with open(f"{Path(__file__).parent}/source_file_compliance/_version.py") as fp:
    exec(fp.read(), pkg_vars)

setuptools.setup(
    name="nx-source-file-compliance",
    python_requires='>=3.9',
    package_dir={"source_file_compliance": "source_file_compliance"},
    packages=["source_file_compliance"],
    include_package_data=True,
    package_data={
        "source_file_compliance": ["config/**"],
    },
    version=pkg_vars["__version__"])
