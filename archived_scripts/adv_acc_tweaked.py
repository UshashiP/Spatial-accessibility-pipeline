import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Load DC ICF data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')

# Load population data
populations = gpd.read_file('blocksandtract_economic_final.shp').to_crs('epsg:26985')

# Fill NaN values for population and socio-economic groups
populations['Bl_totalpo'] = populations['Bl_totalpo'].fillna(0)
populations['PerCapitaI'] = populations['PerCapitaI'].fillna(0)
populations['HI_block'] = populations['HI_block'].fillna(0)
populations['eighteento'] = populations['eighteento'].fillna(0)
populations['65 years a'] = populations['65 years a'].fillna(0)

# Normalize the variables
populations['Bl_totalpo'] = (populations['Bl_totalpo'] - populations['Bl_totalpo'].min()) / (populations['Bl_totalpo'].max() - populations['Bl_totalpo'].min())
populations['PerCapitaI'] = (populations['PerCapitaI'] - populations['PerCapitaI'].min()) / (populations['PerCapitaI'].max() - populations['PerCapitaI'].min())
populations['HI_block'] = (populations['HI_block'] - populations['HI_block'].min()) / (populations['HI_block'].max() - populations['HI_block'].min())
populations['eighteento'] = (populations['eighteento'] - populations['eighteento'].min()) / (populations['eighteento'].max() - populations['eighteento'].min())
populations['65 years a'] = (populations['65 years a'] - populations['65 years a'].min()) / (populations['65 years a'].max() - populations['65 years a'].min())

# Set weights for each factor
weight_population = 0.4
weight_income = 0.3
weight_health = 0.2
weight_age_18to65 = 0.1  # Adjust this weight for the age group 18 to 65
weight_age_65_plus = 0.1  # Adjust this weight for the age group 65 and above

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

for idx, school in schools.iterrows():
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)

    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]

    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            weight_factor = (
                populations.at[i, 'Bl_totalpo'] * weight_population + 
                populations.at[i, 'PerCapitaI'] * weight_income +
                populations.at[i, 'HI_block'] * weight_health +
                populations.at[i, 'eighteento'] * weight_age_18to65 +
                populations.at[i, '65 years a'] * weight_age_65_plus
            )
            weights[idx] += weight_factor * time_decay(distance)

# Calculate accessibility for each census tract and school
accessibility = np.zeros((len(populations), len(schools)))

for school_idx, school in schools.iterrows():
    demand = np.zeros(len(populations))
    school_coords = np.array([school.geometry.centroid.x, school.geometry.centroid.y])
    distances, indices = pop_tree.query(school_coords, k=len(populations), distance_upper_bound=d0_time)

    valid_indices = indices[distances <= d0_time]
    valid_distances = distances[distances <= d0_time]

    for i, distance in zip(valid_indices, valid_distances):
        if i < len(populations) and distance <= d0_time:
            demand[i] = populations.at[i, 'Bl_totalpo'] * time_decay(distance)

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
populations.to_csv("access_ICF_weighted_final.csv", index=False)

# Plot accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))

populations.plot(column='accessibility', cmap='viridis', linewidth=0.5, edgecolor='white', legend=True, ax=ax)
schools.plot(ax=ax, color='red', markersize=5)

ax.set_title('Weighted Accessibility to Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

plt.show()
