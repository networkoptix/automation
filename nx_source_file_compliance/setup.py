import setuptools

setuptools.setup(
    name="nx-source-file-compliance",
    python_requires='>=3.8',
    package_dir={"source_file_compliance": "."},
    packages=["source_file_compliance"],
    include_package_data=True,
    package_data={
        "": ["organization_domains.txt"],
    },
    version='2.2.3')
