from setuptools import setup, find_packages

setup(
    name="spectraPyle",
    version="5.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)