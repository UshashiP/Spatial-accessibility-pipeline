import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Load DC public schools data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

# Load population data
populations = gpd.read_file('blocks_with_income.shp').to_crs('epsg:26985')

# Normalize columns
def normalize_column(df, column):
    return (df[column] - df[column].min()) / (df[column].max() - df[column].min())

#populations['Norm_Total_Popu'] = normalize_column(populations, 'Total Popu')
#populations['Norm_Income'] = normalize_column(populations, 'income_sha')
#populations['Norm_Age'] = normalize_column(populations, 'eighteento')
#populations['Norm_HealthInsurance'] = normalize_column(populations, 'HealthInsurance')
print(populations)

# Set constant scaling factor J
J = 1

# Set distance decay parameter for time
d0_time = 900  # 15 minutes in seconds

# Define distance decay function for time
def time_decay(distance, d0=d0_time):
    return (np.exp(-0.5 * (distance / d0) ** 2) - np.exp(-0.5)) / (1 - np.exp(-0.5))

# Precompute centroid coordinates
schools_coords = np.array(list(schools.geometry.centroid.apply(lambda geom: (geom.x, geom.y))))
populations_coords = np.array(list(populations.geometry.centroid.apply(lambda geom: (geom.x, geom.y))))

# Create spatial index for populations
pop_tree = cKDTree(populations_coords)

# Calculate weights for each school
weights = np.zeros(len(schools))

# Efficiently calculate distances and weights
for idx, school in schools.iterrows():
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)
    
    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]
    
    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            pop_weight = (
                populations.at[i, 'Norm_Total_Popu'] * 
                populations.at[i, 'Norm_Income'] * 
                populations.at[i, 'Norm_Age'] #*
                #populations.at[i, 'Norm_HealthInsurance']
            )
            weights[idx] += pop_weight * time_decay(distance)

# Calculate accessibility for each census tract and school
accessibility = np.zeros((len(populations), len(schools)))

# Efficiently calculate distances and demands
for school_idx, school in schools.iterrows():
    demand = np.zeros(len(populations))
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)
    
    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]
    
    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            pop_weight = (
                populations.at[i, 'Norm_Total_Popu'] * 
                populations.at[i, 'Norm_Income'] * 
                populations.at[i, 'Norm_Age'] #*
                #populations.at[i, 'Norm_HealthInsurance']
            )
            demand[i] = pop_weight * time_decay(distance)
    
    for origin_idx, origin in populations.iterrows():
        origin_coords = np.array([origin.geometry.centroid.x, origin.geometry.centroid.y])
        distances, indices = pop_tree.query(origin_coords, k=len(schools), distance_upper_bound=d0_time)
        
        valid_indices = indices[distances <= d0_time]
        valid_distances = distances[distances <= d0_time]
        
        weight_origin = np.sum([
            weights[valid_idx] * time_decay(distance) 
            for distance, valid_idx in zip(valid_distances, valid_indices) 
            if valid_idx < len(schools) and distance <= d0_time
        ])
        
        supply = school['BEDS']
        demand_j = np.sum(demand[demand > 0])
        
        if demand_j > 0:
            accessibility[origin_idx, school_idx] = J * supply * weight_origin / demand_j
        else:
            accessibility[origin_idx, school_idx] = 0

# Calculate total accessibility for each origin
populations['accessibility'] = np.sum(accessibility, axis=1)

# Save results to a CSV file
populations.to_csv("access_ICF_income_age_health_normalized.csv", index=False)

# Plot accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))

# Plot census tracts with accessibility values
populations.plot(column='accessibility', cmap='viridis', linewidth=0.5, edgecolor='white', legend=True, ax=ax)

# Plot schools on the map
schools.plot(ax=ax, color='red', markersize=5)

# Set axis labels and title
ax.set_title('Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

plt.show()
