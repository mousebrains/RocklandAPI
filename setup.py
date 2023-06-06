from setuptools import find_packages, setup

setup(
    name='hapi',
    version='0.0.1',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'hapi=src.Rockland:main'
        ]
    },
    data_files=[("config", ["src/resources/variable_info.yml"])],
)
