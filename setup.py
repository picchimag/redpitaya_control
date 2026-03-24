from setuptools import setup, find_packages

setup(
    name="python_rp",
    version="0.1.0",
    description="Red Pitaya control and data acquisition",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "numpy>=1.20.0",
        "scipy>=1.7.0",
        "paramiko>=2.7.0",
    ],
)
