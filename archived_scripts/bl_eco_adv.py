import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Load DC public schools data
ICF = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

pd.set_option('display.max_columns', None)

# Load population data
populations = gpd.read_file('blocksandtract_economic.shp').to_crs('epsg:26985')

median_population = populations['Bl_totalpo'].median()
populations['Bl_totalpo'] = populations['Bl_totalpo'].replace(0, median_population)
print(populations)

populations['pop_weight'] = populations['Bl_totalpo'] / populations['Total Popu']

print(populations['pop_weight'])

populations['PerCapitaIncome_block'] = populations['Bl_incomep'] * populations['pop_weight']
print(populations['PerCapitaIncome_block'])
populations['HI_block'] = populations['Bl_healthi'] * populations['pop_weight']
print(populations['HI_block'])

populations['age_18to65_block'] = populations['eighteento'] * populations['pop_weight']
print(populations)

populations.to_file('blocksandtract_economic_final.shp', encoding ='UTF8')



populations['Total Popu'] = (populations['Total Popu'] - populations['Total Popu'].min()) / (populations['Total Popu'].max() - populations['Total Popu'].min())
populations['PerCapitaI'] = (populations['PerCapitaI'] - populations['PerCapitaI'].min()) /(populations['PerCapitaI'].max() - populations['PerCapitaI'].min())
populations['HI_block'] = (populations['HI_block'] - populations['HI_block'].min()) / (populations['HI_block'].max() - populations['HI_block'].min())
populations['age_18to65'] = (populations['age_18to65'] - populations['age_18to65'].min()) /(populations['age_18to65'].max() - populations['age_18to65'].min())
