import logging

import numpy as np
import xarray as xr
import yaml
from pkg_resources import resource_filename


def load_variable_info(file_path: str = None) -> tuple:
    """Load all variable information and generate some useful mapping dicts"""

    if file_path is None:
        file_path = resource_filename(__name__, "resources/variable_info.yml")

    with open(file_path, "r") as f:
        var_info = yaml.safe_load(f)

    expand_variables(var_info)

    id2var = {var_info[key]["typeID"]: key for key in var_info}
    # var2id = {key:id2var[key] for key in id2var}

    return var_info, id2var  # , var2id


def expand_variables(var_info: dict) -> None:
    """Some variables cover a wide range of type IDs denoted as a list in the
    yaml file. This function modifies the dictionary in place."""

    numeric_list = [str(i) for i in range(1, 16)]
    xyz_list = ["x", "y", "z"]

    keys_to_expand = []
    for key in var_info:
        if type(var_info[key]["typeID"]) is list:
            keys_to_expand.append(key)

    for key in keys_to_expand:
        info = var_info.pop(key)
        expand = info.pop("expand", "123")

        if expand == "123":
            classifyer = numeric_list
        elif expand == "xyz":
            classifyer = xyz_list
        else:
            raise RuntimeError(f"Unknown expansion specified, {expand}")

        ID_range = info.pop("typeID")
        long_name = info.pop("long_name")

        for i, typeID in enumerate(range(ID_range[0], ID_range[1] + 1)):
            cl = classifyer[i]
            var_info[key + cl] = dict(
                typeID=typeID, long_name=long_name + " " + cl, **info
            )


def generate_index_mapping(id2var: dict, ids: list) -> tuple:
    """This function generates a dictionary mapping from variable name to data
    list index using available data type ids"""
    var2idx = {id2var[id]: idx for idx, id in enumerate(ids)}
    # idx2var = {var2idx[var]:var for var in var2idx}
    return var2idx  # , idx2var


def extract_profile_dimensions(json_body: dict, var2idx: dict) -> tuple:
    data = json_body["data"]
    ids = json_body["typeIds"]

    n_vars = len(ids)
    n_times = len(data[var2idx["time"]][0])

    return n_vars, n_times


def parse_NaN(dat: list) -> list:
    """Recusively replace "NaN" strings with floats"""
    out = []
    for el in dat:
        if type(el) is list:
            out.append(parse_NaN(el))
        else:
            out.append(float(el))
    return out


def profile_to_Dataset(json_body: dict, file_path: str = None) -> xr.Dataset:
    """"""
    CF_attributes = ["long_name", "standard_name", "units"]
    data = json_body["data"]

    var_info, id2var = load_variable_info(file_path)

    var2idx = generate_index_mapping(id2var, json_body["typeIds"])
    n_vars, n_times = extract_profile_dimensions(json_body, var2idx)

    logging.info("variables %s", {hex(var_info[key]["typeID"]): key for key in var2idx})
    logging.info("n_vars %i", n_vars)
    logging.info("n_times %i", n_times)

    # Reduce info to only the downloaded variables and sort them
    var_info = {key: var_info[key] for key in var2idx}
    logging.info("var_info\n%s", var_info)

    # Find coordinate and data variables. Coordinate variable names match their dimension name.
    coord_keys = [key for key in var_info if key == var_info[key]["dims"]]
    data_keys = sorted(list(set(var_info.keys()) - set(coord_keys)))

    # Generate coordinates
    coords = {}
    for key in coord_keys:
        logging.info("creating coord %s", key)
        info = var_info[key]
        attrs = {at: info[at] for at in CF_attributes}
        coords[key] = (info["dims"], data[var2idx[key]][0], attrs)

    # The second index should be the coord data
    ntime = np.size(coords["time"][1])

    n = 0
    time_dim_lengths = [ntime]
    time_dim_names = ["time"]
    # Generate data variables
    data_vars = {}
    for key in data_keys:
        logging.info("data variable %s", key)
        info = var_info[key]
        logging.info("data variable info %s", info)
        attrs = {at: info[at] for at in CF_attributes}

        if type(info["dims"]) is list:
            dat = data[var2idx[key]]
        else:
            dat = data[var2idx[key]][0]

        dat = parse_NaN(dat)

        # Check the time dimension matches
        nrow = np.size(dat, axis=0)
        dim_length_mismatch = nrow != ntime
        dims = [info["dims"]] if type(info["dims"]) is str else info["dims"].copy()

        # Rename time if dimensions mismatch
        if dim_length_mismatch:
            if nrow not in time_dim_lengths:
                n += 1
                time_dim_lengths.append(nrow)
                time_dim_names.append(f"time{n}")
                
        name = np.asarray(time_dim_names)[
            np.asarray(time_dim_lengths) == nrow
        ].item()

        for i in range(len(dims)):
            if "time" == dims[i]:
                dims[i] = name

        data_vars[key] = (dims, dat, attrs)

    logging.info("returning xarray.Dataset")
    return xr.Dataset(data_vars, coords)
