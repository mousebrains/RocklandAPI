#! /usr/bin/env python3

import json
import xarray as xr
import yaml
import logging
import numpy as np


def load_variable_info(file_path:str="variable_info.yml") -> tuple:
    """Load all variable information and generate some useful mapping dicts"""
    with open(file_path, "r") as f:
        var_info = yaml.safe_load(f)

    expand_variables(var_info)

    id2var = {var_info[key]["typeID"]:key for key in var_info}
    # var2id = {key:id2var[key] for key in id2var}

    return var_info, id2var  #, var2id


def expand_variables(var_info:dict) -> None:
    """Some variables cover a wide range of type IDs denoted as a list in the
    yaml file. This function modifies the dictionary in place."""

    numeric_list = [str(i) for i in range(1, 16)]
    xyz_list = ["x", "y", "z"]

    keys_to_expand = []
    for key in var_info:
        if type(var_info[key]["typeID"]) is list: keys_to_expand.append(key)

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
            var_info[key + cl] = dict(typeID=typeID, long_name=long_name + " " + cl, **info)


def generate_index_mapping(id2var:dict, ids:list) -> tuple:
    """This function generates a dictionary mapping from variable name to data
    list index using available data type ids"""
    var2idx = {id2var[id]:idx for idx, id in enumerate(ids)}
    # idx2var = {var2idx[var]:var for var in var2idx}
    return var2idx  #, idx2var


def extract_profile_dimensions(json_body:dict, var2idx:dict) -> tuple:
    data = json_body["data"]
    ids = json_body["typeIds"]

    n_vars = len(ids)
    n_times = len(data[var2idx["time"]][0])

    return n_vars, n_times


def parse_NaN(dat:list) -> list:
    """Recusively replace "NaN" values with numpy.NaN objects"""
    out = []
    for el in dat:
        if type(el) is list:
            out.append(parse_NaN(el))
        elif el == "NaN":
            out.append(np.NaN)
        else:
            out.append(el)
    return out


def profile_to_xrDataset(json_body:dict) -> xr.Dataset:
    """"""
    CF_attributes = ["long_name", "standard_name", "units"]
    data = json_body["data"]

    var_info, id2var = load_variable_info()

    var2idx = generate_index_mapping(id2var, json_body["typeIds"])
    n_vars, n_times = extract_profile_dimensions(json_body, var2idx)

    logging.info("variables %s", {hex(var_info[key]["typeID"]):key for key in var2idx})
    logging.info("n_vars %i", n_vars)
    logging.info("n_times %i", n_times)

    # Reduce info to only the downloaded variables and sort them
    var_info = {key:var_info[key] for key in var2idx}
    logging.info("var_info\n%s", var_info)

    # Find coordinate and data variables. Coordinate variable names match their dimension name.
    coord_keys = [key for key in var_info if key == var_info[key]["dims"]]
    data_keys = sorted(list(set(var_info.keys()) - set(coord_keys)))

    # Generate coordinates
    coords = {}
    for key in coord_keys:
        logging.info("creating coord %s", key)
        info = var_info[key]
        attrs = {at:info[at] for at in CF_attributes}
        coords[key] = (info["dims"], data[var2idx[key]][0], attrs)

    # Generate data variables
    data_vars = {}
    for key in data_keys:
        logging.info("creating data_var %s", key)
        info = var_info[key]
        attrs = {at:info[at] for at in CF_attributes}

        if type(info["dims"]) is list:
            dat = data[var2idx[key]]
        else:
            dat = data[var2idx[key]][0]

        dat = parse_NaN(dat)

        data_vars[key] = (info["dims"], dat, attrs)

    logging.info("returning xarray.Dataset")
    return xr.Dataset(data_vars, coords)


if __name__ == "__main__":

    with open("info.json", "r") as f:
        profile = json.load(f)

    body = profile["body"][0]  # First profile

    profile_to_xrDataset(body).to_netcdf("test.nc")
