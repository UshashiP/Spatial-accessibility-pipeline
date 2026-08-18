
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

populations= pd.read_csv("access_ICF_totalpopu1.csv")
pri_df = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
print(populations)
fig, ax = plt.subplots(figsize=(12, 10))

# plot census tracts with accessibility values
populations.plot(column='accessibility', cmap='Accent', linewidth=0.5,legend=False,)

# plot schools on the map

# plot population centers with accessibility values

# plot schools on the map
pri_df.plot(ax=ax, color='red', markersize=5)

# set axis labels and title
ax.set_title('Accessibility for eighteento65 to Intermediate_Care_Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

plt.show()