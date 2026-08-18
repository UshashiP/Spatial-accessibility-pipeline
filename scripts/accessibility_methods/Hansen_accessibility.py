import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load the data
schools = gpd.read_file('../../data/shapefiles/Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
populations = gpd.read_file('../../data/shapefiles/blocks_with_income.shp').to_crs('epsg:26985')

# Define a custom decay function (e.g., exponential decay)
def exponential_decay(distance, alpha=0.001):
    return np.exp(-alpha * distance)

# Initialize a column for Hansen accessibility
populations['hansen_accessibility'] = 0

# Calculate Hansen accessibility
for i, tract in populations.iterrows():
    hansen_sum = 0
    for idx, school in schools.iterrows():
        distance = tract.geometry.distance(school.geometry)
        hansen_sum += school['BEDS'] * exponential_decay(distance)
    populations.at[i, 'hansen_accessibility'] = hansen_sum

# Save results to a CSV file
populations.to_csv("../../outputs/results/access_ICF_hansen.csv", index=False)

# Plot Hansen accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))
populations.plot(column='hansen_accessibility', cmap='RdYlBu', linewidth=0.5, edgecolor='white', legend=True, ax=ax)
schools.plot(ax=ax, color='red', markersize=5)
ax.set_title('Hansen Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.tight_layout()
plt.savefig('../../outputs/figures/hansen_accessibility.png', dpi=300, bbox_inches='tight')
print("Figure saved to outputs/figures/hansen_accessibility.png")
plt.show()
schools.plot(ax=ax, color='blue', markersize=7)
ax.set_title('Hansen Accessibility for Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.show()
