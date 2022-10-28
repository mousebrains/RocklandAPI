#! /usr/bin/env python3

import json
import xarray as xr
import yaml
import logging


def load_var_mapping(file_path:str="variable_mapping.yml") -> tuple:
    """The variable map is a dict that maps data type id to variable name"""
    with open(file_path, "r") as f:
        id2var = yaml.safe_load(f)

    # Reverse mapping
    var2id = {id2var[id]:id for id in id2var}

    return id2var, var2id


def generate_index_mapping(id2var:dict, ids:list) -> tuple:
    """This function generates a dictionary mapping from variable name to data
    list index using available data type ids"""
    var2idx = {id2var[id]:idx for idx, id in enumerate(ids)}
    idx2var = {var2idx[var]:var for var in var2idx}
    return var2idx, idx2var


def extract_profile_dimensions(json_body:dict, var2idx:dict) -> tuple:
    data = json_body["data"]
    ids = json_body["typeIds"]

    n_vars = len(ids)
    n_depths = len(data[var2idx["p"]][0])

    return n_vars, n_depths


def profile_to_xrDataset(json_body:dict) -> xr.Dataset:
    """"""
    data = json_body["data"]

    id2var, var2id = load_var_mapping()

    var2idx, idx2var = generate_index_mapping(id2var, json_body["typeIds"])
    n_vars, n_depths = extract_profile_dimensions(json_body, var2idx)

    logging.info("variables %s", {hex(var2id[key]):key for key in var2idx})
    logging.info("n_vars %i", n_vars)
    logging.info("n_depths %i", n_depths)

    data_vars = {
        "p": (["profile", "time"], data[var2idx["p"]]),
        "eps1": (["profile", "time"], data[var2idx["eps1"]])
    }

    coords = {
        "time": ("time", data[var2idx["time"]][0], {"units": "seconds since 1970-01-01"})
    }

    return xr.Dataset(data_vars, coords)


if __name__ == "__main__":

    with open("info.json", "r") as f:
        profile = json.load(f)

    body = profile["body"][0]  # First profile

    profile_to_xrDataset(body).to_netcdf("test.nc")

    #
    # id2var, var2id = load_var_mapping()
    #
    # for idx, item in enumerate(body["data"]):
    #     id = body["typeIds"][idx]
    #
    #     try:
    #         var_name = id2var[id]
    #     except KeyError:
    #         var_name = "unkown"
    #
    #     print(f"ID: {id}, var: {var_name}, len:{len(item)}")
    #     print("Element lengths:")
    #     for l in item:
    #         print(f"  {len(l)}")
