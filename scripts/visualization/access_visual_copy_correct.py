#######code working fine########


import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

populations= pd.read_csv("access_ICF_totalpopu1.csv")
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')


dc_map = gpd.read_file('Census_Blocks_in_2020.shp').to_crs('epsg:26985')

dc_map['GEOID'] = dc_map['GEOID'].astype('int64')

merged_data = dc_map.merge(populations, on='GEOID')
merged_data = gpd.GeoDataFrame(merged_data)

# Get a list of column names to keep (those not ending with "_y")
#columns_to_keep = [col for col in merged_data.columns if not (col.endswith("_y") or col.startswith("P00") or col.startswith("H00")or col.startswith("POP") or col.startswith("HU"))]

# Filter the GeoDataFrame to keep only the selected columns
#merged_data_filtered = merged_data[columns_to_keep]
# Save the filtered GeoDataFrame to a new CSV file
merged_data.to_csv('merged_data.csv', index=False)

merged_data= merged_data.set_geometry('geometry_x')

fig, ax = plt.subplots(figsize=(10, 10))
merged_data.plot(column='Accessibility', cmap='twilight', ax=ax, edgecolor='black', linewidth=0.2, legend=True)
schools.plot(ax=ax, color='red', markersize=5)

ax.set_title('Accessibility to ICFs in DC')
plt.show()
