# rapi - The Rockland Scientific API command line interface and wrapper

This package simplifies interfacing with the Rockland Cloud, which is used for processing in situ data from microstructure gliders. 

## Requirements

This package uses `requests` for HTTP requests and `xarray` with `netcdf4` to write data. 

## Installation

Install with `pip`:

pip install git+https://github.com/mousebrains/RocklandAPI.git

After installation you will have acess to the command line interface (CLI), e.g.

```
rapi project list
rapi download --directory="save_to" PROJ
```

By default, configuration files are stored in `~/.config/Rockland`

If the file `credentials.yaml` does not exist in the configuration directory, you will be prompted for a username, password, and organization.

To create a project use:
`rapi project create probar "Probar un proyecto" 123`

To list existing projects use:
`rapi project list`

This project is still in development. To enable debugging, use the `--debug` option, e.g.
`rapi --debug project delete probar`

## Scripting

`rapi` may also be used in a scipt, e.g.

```python
from pathlib import Path
from rapi import RAPI

mapping = {
    "project": RAPI.Project,
    "upload": RAPI.Upload,
    "download": RAPI.Download,
}

project = "A686"

data_dir = Path("Dockserver/glider/from-glider")
save_dir = Path("out")

parser = RAPI.mkParser()

# Upload one by one
mri_files = data_dir.glob("*.mri")
for file in mri_files:
    print(f"Uploading {file.name}")
    # Recreate command line argument
    args = parser.parse_args(["upload", project, str(file)])
    RAPI.run(args)
```

## conda environment

The API requires some non-standard python packages, such as `requests`. These can be installed into a conda environment using:
`conda env create -f environment.yml`
