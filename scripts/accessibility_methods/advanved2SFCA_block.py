
###########Enhanced 2SFCA Implementation#######

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load DC Intermediate Care Facilities data
schools = gpd.read_file('../../data/shapefiles/Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

# Load population data
populations = gpd.read_file('../../data/shapefiles/blocks_with_income.shp').to_crs('epsg:26985')

print(f"Loaded {len(schools)} facilities and {len(populations)} census blocks")

# Set constant scaling factor J
J = 1

# Set distance threshold and decay parameter
d0 = 900  # 900 meters threshold

# Define distance decay function
def time_decay(distance, d0=d0):
    if distance > d0:
        return 0
    return (np.exp(-0.5 * (distance/d0)**2) - np.exp(-0.5)) / (1 - np.exp(-0.5))

print("\n=== Step 1: Calculate supply-to-demand ratio for each facility ===")

# Step 1: For each facility, calculate supply-to-demand ratio (R_j)
supply_demand_ratio = {}

for facility_idx, facility in schools.iterrows():
    # Calculate weighted demand within catchment area
    total_weighted_demand = 0
    
    for pop_idx, pop_location in populations.iterrows():
        distance = facility.geometry.distance(pop_location.geometry)
        
        if distance <= d0:
            population = pop_location['Total Popu']
            weight = time_decay(distance)
            total_weighted_demand += population * weight
    
    # Calculate supply-to-demand ratio
    if total_weighted_demand > 0:
        supply = facility['BEDS']
        supply_demand_ratio[facility_idx] = J * supply / total_weighted_demand
    else:
        supply_demand_ratio[facility_idx] = 0
    
    if facility_idx % 20 == 0:
        print(f"Processed facility {facility_idx + 1}/{len(schools)}")

print(f"\nCalculated supply-to-demand ratios for {len(supply_demand_ratio)} facilities")

print("\n=== Step 2: Calculate accessibility for each population location ===")

# Step 2: For each population location, sum weighted supply-to-demand ratios
accessibility_scores = []

for pop_idx, pop_location in populations.iterrows():
    accessibility_score = 0
    
    for facility_idx, facility in schools.iterrows():
        distance = pop_location.geometry.distance(facility.geometry)
        
        if distance <= d0:
            weight = time_decay(distance)
            accessibility_score += supply_demand_ratio[facility_idx] * weight
    
    accessibility_scores.append(accessibility_score)
    
    if pop_idx % 1000 == 0:
        print(f"Processed population location {pop_idx + 1}/{len(populations)}")

# Add accessibility scores to populations dataframe
populations['accessibility'] = accessibility_scores

print(f"\n=== Results ===")
print(f"Accessibility scores calculated for {len(populations)} locations")
print(f"Mean accessibility: {populations['accessibility'].mean():.6f}")
print(f"Max accessibility: {populations['accessibility'].max():.6f}")
print(f"Min accessibility: {populations['accessibility'].min():.6f}")
print(f"Locations with zero accessibility: {(populations['accessibility'] == 0).sum()}")

# Save results to a CSV file
populations.to_csv("../../outputs/results/access_ICF_totalpopu.csv", index=False)
print("\nResults saved to outputs/results/access_ICF_totalpopu.csv")

print("\n=== Creating visualization ===")

# Plot accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))

# Plot census blocks with accessibility values
populations.plot(column='accessibility', cmap='viridis', linewidth=0.5, 
                edgecolor='white', legend=True, ax=ax, 
                legend_kwds={'label': 'Accessibility Score'})

# Plot facilities on the map
schools.plot(ax=ax, color='red', markersize=20, marker='*', 
            label='Intermediate Care Facilities')

# Set axis labels and title
ax.set_title('Enhanced 2SFCA Accessibility to Intermediate Care Facilities in DC', 
            fontsize=16, fontweight='bold')
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)
ax.legend()

plt.tight_layout()
plt.savefig('../../outputs/figures/enhanced_2sfca_accessibility.png', dpi=300, bbox_inches='tight')
print("Figure saved to outputs/figures/enhanced_2sfca_accessibility.png")
plt.show()

print("\nAnalysis complete!")
