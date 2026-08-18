import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

#Load DC public schools data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

#Load population data
populations = gpd.read_file('blocks_with_income.shp').to_crs('epsg:26985')
print(populations)
#Set constant scaling factor J
J = 1

#Set distance decay parameter for time
d0_time = 900  # 15 minutes in seconds

# Define distance decay function for time
def time_decay(distance, d0=d0_time):
    return (np.exp(-0.5 * (distance / d0) ** 2) - np.exp(-0.5)) / (1 - np.exp(-0.5))

#Precompute centroid coordinates
schools_coords = np.array(list(schools.geometry.centroid.apply(lambda geom: (geom.x, geom.y))))
populations_coords = np.array(list(populations.geometry.centroid.apply(lambda geom: (geom.x, geom.y))))

#Create spatial index for populations
pop_tree = cKDTree(populations_coords)

#Calculate weights for each school
weights = np.zeros(len(schools))
#print(f"School {idx} - Valid Distances: {valid_distances}")
#print(f"School {idx} - Valid Indices: {valid_indices}")
    
#Efficiently calculate distances and weights
for idx, school in schools.iterrows():
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)
    
    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]
    
    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            weights[idx] += populations.at[i, 'Total Popu'] * time_decay(distance)
#print(f"Distance: {distance}, Weight: {weights}, Population index: {i}")
#print(f"Length of weights array: {len(weights)}")  

#Calculate accessibility for each census tract and school
accessibility = np.zeros((len(populations), len(schools)))

#Efficiently calculate distances and demands
for school_idx, school in schools.iterrows():
    demand = np.zeros(len(populations))
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)
    
    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]
    
    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            demand[i] = populations.at[i, 'Total Popu'] * time_decay(distance)
    
    for origin_idx, origin in populations.iterrows():
        origin_coords = np.array([origin.geometry.centroid.x, origin.geometry.centroid.y])
        distances, indices = pop_tree.query(origin_coords, k=len(schools), distance_upper_bound=d0_time)
        
        valid_indices = indices[distances <= d0_time]
        valid_distances = distances[distances <= d0_time]
        
        weight_origin = np.sum([weights[valid_idx] * time_decay(distance) for distance, valid_idx in zip(valid_distances, valid_indices) if valid_idx < len(schools) and distance <= d0_time])
        
        supply = school['BEDS']
        demand_j = np.sum(demand[demand > 0])
        
        if demand_j > 0:
            accessibility[origin_idx, school_idx] = J * supply * weight_origin / demand_j
        else:
            accessibility[origin_idx, school_idx] = 0

#Calculate total accessibility for each origin
populations['accessibility'] = np.sum(accessibility, axis=1)
print(populations['accessibility'] )
#Save results to a CSV file
populations.to_csv("access_ICF_totalpopu_optimized.csv", index=False)

#Plot accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))

#Plot census tracts with accessibility values
populations.plot(column='accessibility', cmap='Accent', linewidth=0.5, edgecolor='white', legend=True, ax=ax)

#Plot schools on the map
schools.plot(ax=ax, color='red', markersize=5)

#Set axis labels and title
ax.set_title('Accessibility for eighteento65 to Intermediate_Care_Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

# Adjust legend position
#leg = ax.get_legend()
##leg.set_bbox_to_anchor((1, 0.5))

plt.show()
