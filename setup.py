from setuptools import find_packages, setup

setup(
    name='rapi',
    version='0.0.1',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'rapi=rapi.RAPI:main'
        ]
    },
    data_files=[("config", ["rapi/resources/variable_info.yml"])],
    install_requires=[
        "xarray",
        "netcdf4",
        "requests",
    ]
)
