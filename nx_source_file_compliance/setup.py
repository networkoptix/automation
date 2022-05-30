from pathlib import Path
import setuptools

pkg_vars = {}
with open(f"{Path(__file__).parent}/_version.py") as fp:
    exec(fp.read(), pkg_vars)

setuptools.setup(
    name="nx-source-file-compliance",
    python_requires='>=3.8',
    package_dir={"source_file_compliance": "."},
    packages=["source_file_compliance"],
    include_package_data=True,
    package_data={
        "": ["organization_domains.txt"],
    },
    version=pkg_vars["__version__"])
