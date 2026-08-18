import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load the data
schools = gpd.read_file('../../data/shapefiles/Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
populations = gpd.read_file('../../data/shapefiles/blocks_with_income.shp').to_crs('epsg:26985')

# Define distance decay parameter for gravity model
beta = 0.5  # You can adjust this parameter

# Initialize a column for gravity-based accessibility
populations['gravity_accessibility'] = 0

# Calculate gravity-based accessibility
for i, tract in populations.iterrows():
    gravity_sum = 0
    for idx, school in schools.iterrows():
        distance = tract.geometry.distance(school.geometry)
        gravity_sum += school['BEDS'] * np.exp(-beta * distance)
    populations.at[i, 'gravity_accessibility'] = gravity_sum

# Save results to a CSV file
populations.to_csv("../../outputs/results/access_ICF_gravity.csv", index=False)

# Plot gravity-based accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))
populations.plot(column='gravity_accessibility', cmap='RdYlBu', linewidth=0.5, edgecolor='white', legend=True, ax=ax)
schools.plot(ax=ax, color='red', markersize=5)
ax.set_title('Gravity-Based Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.tight_layout()
plt.savefig('../../outputs/figures/gravity_accessibility.png', dpi=300, bbox_inches='tight')
print("Figure saved to outputs/figures/gravity_accessibility.png")
plt.show()
ax.set_title('Gravity-based Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.show()
