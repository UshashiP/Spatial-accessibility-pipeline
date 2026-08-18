###testing influence of independent variables on accessibility


import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
import statsmodels.api as sm

# Load DC public schools data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
pd.set_option('display.max_columns', None)

# Load population data
populations = gpd.read_file('access_regression_output.shp').to_crs('epsg:26985')
print(populations)


X = populations[['popbl_norm','I_blnorm','HIbl_norm', 'agebl_norm']]
y = populations['accessibil']
X = sm.add_constant(X)
model = sm.OLS(y, X).fit()

print(model.summary())

