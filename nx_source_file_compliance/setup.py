import setuptools

setuptools.setup(
    name="nx-source-file-compliance",
    python_requires='>=3.8',
    package_dir={"source_file_compliance": "."},
    packages=["source_file_compliance"],
    include_package_data=True,
    package_data={
        "": ["organizations_domains.txt"],
    },
    version='2.0.0')
