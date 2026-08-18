####predicting the block level dependent variables by regression

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from sklearn.linear_model import LinearRegression

# Load DC public schools data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
pd.set_option('display.max_columns', None)

# Load population data
populations = gpd.read_file('blocksandtract_economic_final.shp').to_crs('epsg:26985')

populations['Bl_totalpo']= populations['Bl_totalpo'].fillna(0)
populations['eighteento']= populations['eighteento'].fillna(0)
populations['Bl_incomep']= populations['Bl_incomep'].fillna(0)
populations['Bl_healthi'] = populations['Bl_healthi'].fillna(0)
populations

populations=populations.rename(columns={'eighteento': 'age_18to65_tract'})
populations=populations.rename(columns={'Bl_incomep': 'income_tract'})
populations=populations.rename(columns={'Bl_healthi': 'HI_tract'})

block_data = populations[['BLOCK', 'TRACT', 'Bl_totalpo', 'age_18to65_tract', 'income_tract', 'HI_tract']]

# Initialize the regression model
model = LinearRegression()

# Fit the regression model for age
X = block_data[['Bl_totalpo']]
y_age = block_data['age_18to65_tract']
model.fit(X, y_age)
block_data['age_18to65_bl_pred'] = model.predict(X)

# Fit the regression model for income
y_income = block_data['income_tract']
model.fit(X, y_income)
block_data['PerCapitaI_bl_pred'] = model.predict(X)

# Fit the regression model for health insurance
y_health_insurance = block_data['HI_tract']
model.fit(X, y_health_insurance)
block_data['HI_block_pred'] = model.predict(X)



# Group by tract and calculate the total for each variable
tract_totals = block_data.groupby('TRACT').agg({
    'age_18to65_tract': 'sum',
    'income_tract': 'sum',
    'HI_tract': 'sum',
    'age_18to65_bl_pred': 'sum',
    'PerCapitaI_bl_pred': 'sum',
    'HI_block_pred': 'sum'
}).reset_index()

# Merge tract_totals back to block_data
block_data = block_data.merge(tract_totals, on='TRACT', suffixes=('', '_tract_total'))

# Adjust block-level predictions to match tract totals
block_data['age_18to65_block'] = block_data['age_18to65_bl_pred'] * (block_data['age_18to65_tract'] / block_data['age_18to65_bl_pred_tract_total'])
block_data['PerCapitaI_block'] = block_data['PerCapitaI_bl_pred'] * (block_data['income_tract'] / block_data['PerCapitaI_bl_pred_tract_total'])
block_data['HI_block'] = block_data['HI_block_pred'] * (block_data['HI_tract'] / block_data['HI_block_pred_tract_total'])



# Replace initial block-level columns with adjusted values
populations['age_18to65_block'] = block_data['age_18to65_block']
populations['PerCapitaI_block'] = block_data['PerCapitaI_block']
populations['HI_block'] = block_data['HI_block']

populations['popbl_norm'] = (populations['Bl_totalpo'] - populations['Bl_totalpo'].min()) /(populations['Bl_totalpo'].max() - populations['Bl_totalpo'].min())
populations['agebl_norm'] = (populations['age_18to65_block'] - populations['age_18to65_block'].min()) /(populations['age_18to65_block'].max() - populations['age_18to65_block'].min())
populations['I_blnorm'] = (populations['PerCapitaI_block'] - populations['PerCapitaI_block'].min()) /(populations['PerCapitaI_block'].max() - populations['PerCapitaI_block'].min())
populations['HIbl_norm'] = (populations['HI_block'] - populations['HI_block'].min()) / (populations['HI_block'].max() - populations['HI_block'].min())
print(populations)

##populations.to_file('regression_variables.shp', encoding='UTF8')

