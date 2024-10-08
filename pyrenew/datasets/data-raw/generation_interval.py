# Dataset from:
# https://raw.githubusercontent.com/CDCgov/wastewater-informed-covid-forecasting/0962c5d1652787479ac72caebf076ab55fe4e10c/input/saved_pmfs/generation_interval.csv

# numpydoc ignore=GL08

import os

import polars as pl

gen_int = pl.read_csv(
    "https://raw.githubusercontent.com/CDCgov/wastewater-informed-covid-forecasting/0962c5d1652787479ac72caebf076ab55fe4e10c/input/saved_pmfs/generation_interval.csv",
)

# Building path to save the file
path = os.path.join(
    "pyrenew",
    "datasets",
    "gen_int.tsv",
)

os.makedirs(os.path.dirname(path), exist_ok=True)

gen_int.write_csv(
    file=path,
    separator="\t",
    include_header=True,
    null_value="",
)
