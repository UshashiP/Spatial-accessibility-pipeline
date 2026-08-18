
###########Enhanced 2SFCA Implementation#######

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Resolve data paths relative to this script's location, not the working directory
_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR.parents[1] / "data" / "shapefiles"

# Load DC Intermediate Care Facilities data
#schools = gpd.read_file(_DATA_DIR / 'Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

# Load population data
populations = gpd.read_file(_DATA_DIR / 'blocksandtract_economic_final.shp').to_crs('epsg:26985')

print(populations.head())

####code for methodology 
plt.show()

print("\nAnalysis complete!")
