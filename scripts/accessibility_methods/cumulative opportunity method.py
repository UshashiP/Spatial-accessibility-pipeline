import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load the data
schools = gpd.read_file('../../data/shapefiles/Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
populations = gpd.read_file('../../data/shapefiles/blocks_with_income.shp').to_crs('epsg:26985')

# Define distance threshold (e.g., 900 meters)
distance_threshold = 900

# Initialize a column for cumulative opportunity accessibility
populations['cumulative_opportunity'] = 0

# Calculate the number of facilities within the distance threshold
for i, tract in populations.iterrows():
    count = 0
    for idx, school in schools.iterrows():
        distance = tract.geometry.distance(school.geometry)
        if distance <= distance_threshold:
            count += 1
    populations.at[i, 'cumulative_opportunity'] = count

# Save results to a CSV file
populations.to_csv("../../outputs/results/access_ICF_cumulative_opportunity.csv", index=False)

# Plot cumulative opportunity accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))
populations.plot(column='cumulative_opportunity', cmap='RdYlBu', linewidth=0.5, edgecolor='white', legend=True, ax=ax)
schools.plot(ax=ax, color='red', markersize=5)
ax.set_title('Cumulative Opportunity Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.tight_layout()
plt.savefig('../../outputs/figures/cumulative_opportunity_accessibility.png', dpi=300, bbox_inches='tight')
print("Figure saved to outputs/figures/cumulative_opportunity_accessibility.png")
plt.show()
schools.plot(ax=ax, color='blue', markersize=7)
ax.set_title('Cumulative Opportunity Accessibility for Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
plt.show()
