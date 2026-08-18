import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

populations= pd.read_csv("access_ICF_final1.csv")
populations

populations = populations.head(1000)

populations.to_csv('access_short.csv', index=False)

icf = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')


icf=icf.to_csv('icf.csv', index=False)