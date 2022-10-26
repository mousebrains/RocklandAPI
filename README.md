# Implementation of Rockland Cloud API for transferring data to/from Rockland's cloud

Rockland.py handles talking to the Rockland Cloud using the Rockland Cloud API.

By default, configuration files are stored in `~/.config/Rockland`

If the file `credentials.yaml` does not exist in the configuration directory, you will be prompted for a username, password, and organization.

To create a project use:
`./Rockland.py --debug project create probar "Probar un proyecto" 123`

To list existing projects use:
`./Rockland.py --debug project list`

This code has only been tested on a MacOS system, so far. Jesse found that this works with python 3.10 but not 3.8.

## conda environment

The API requires some non-standard python packages, such as `requests`. These can be installed into a conda environment using:
`conda env create -f environment.yml`

To use the API, activate the environment with,
`conda activate rapi`

Then the commands above should work, e.g.
`./Rockland.py --debug project list`
