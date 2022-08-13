from datetime import datetime
import shutil
from pam import read, write, core
import os

def pop_combine(
    inpaths: str,
    matsim_version: int,
    simplify_pt_trips: bool = False,
    autocomplete : bool = True,
    crop: bool = False,
    leg_attributes: bool = True,
    leg_route: bool = True,
    ):

    """
    Combine two or more populations (e.g. household, freight... etc).

    """
    print("==================================================")
    print(f"Combining input populations")

    combined_population = core.Population()

    for inpath in inpaths:

        population = read.read_matsim(
            inpath,
            household_key="hid",
            weight=1,
            version=matsim_version,
            simplify_pt_trips=simplify_pt_trips,
            autocomplete=autocomplete,
            crop=crop,
            leg_attributes=leg_attributes,
            leg_route=leg_route,
            )
        print(f"population: {population.stats}")

        combined_population += population

    return combined_population
