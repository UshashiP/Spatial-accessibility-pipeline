#####code working fine####
####final advanced block and economic data code
###data engineering tasks were performed separately

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Load DC ICF data
schools = gpd.read_file('/Users/ushashi/Documents/codes/Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
pd.set_option('display.max_columns', None)

# Load population data
populations = gpd.read_file('/Users/ushashi/Documents/codes/blocksandtract_economic_final.shp').to_crs('epsg:26985')
populations

populations['Bl_totalpo']= populations['Bl_totalpo'].fillna(0)
populations['PerCapitaI']= populations['PerCapitaI'].fillna(0)
populations['HI_block']= populations['HI_block'].fillna(0)
populations['age_18to65'] = populations['age_18to65'].fillna(0)

# Normalize the additional variables
populations['Bl_totalpo'] = (populations['Bl_totalpo'] - populations['Bl_totalpo'].min()) / (populations['Bl_totalpo'].max() - populations['Bl_totalpo'].min())
populations['PerCapitaI'] = (populations['PerCapitaI'] - populations['PerCapitaI'].min()) /(populations['PerCapitaI'].max() - populations['PerCapitaI'].min())
populations['HI_block'] = (populations['HI_block'] - populations['HI_block'].min()) / (populations['HI_block'].max() - populations['HI_block'].min())
populations['age_18to65'] = (populations['age_18to65'] - populations['age_18to65'].min()) /(populations['age_18to65'].max() - populations['age_18to65'].min())

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
            weight_factor = (
                populations.at[i, 'Total Popu'] + 
                populations.at[i, 'PerCapitaI'] +
                populations.at[i, 'HI_block'] +
                populations.at[i, 'age_18to65']
            )
            weights[idx] += weight_factor * time_decay(distance)

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
            demand[i] = populations.at[i, 'Total Popu'] * time_decay(distance)
    
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
        #print(f"Origin {origin_idx} - Demand: {demand_j}")

        if demand_j > 0:
            accessibility[origin_idx, school_idx] = J * supply * weight_origin / demand_j
        else:
            accessibility[origin_idx, school_idx] = 0

print("NaN values in accessibility array:")
print(np.isnan(accessibility).sum())

# Calculate total accessibility for each origin
populations['accessibility'] = np.sum(accessibility, axis=1)

# Check for NaN values in the total accessibility column
print("NaN values in total accessibility column:")
print(populations['accessibility'].isnull().sum())
#populations['accessibility']=populations['accessibility'].fillna(0)
print(populations['accessibility'])
# Save results to a CSV file
populations.to_csv("access_ICF_final1.csv", index=False)
sort = populations.sort_values(by='accessibility', ascending=False)
pd.set_option('display.max_columns', None)

print(sort)

blocks_with_zero_accessibility = sort[sort['accessibility'] == 0]

# Get the total number of such blocks
total_blocks_with_zero_accessibility = len(blocks_with_zero_accessibility)

# Display the result
print("Total number of blocks with accessibility score of 0:", total_blocks_with_zero_accessibility)

print(populations.columns)


# Plot accessibility on the map
fig, ax = plt.subplots(figsize=(12, 10))

# Plot census tracts with accessibility values
populations.plot(column='accessibility', cmap='RdYlBu', linewidth=0.5, edgecolor='white', legend=True, ax=ax)

# Plot schools on the map
schools.plot(ax=ax, color='blue', markersize=5)

# Set axis labels and title
ax.set_title('Accessibility for Intermediate Care Facilities in DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

plt.show()

# Normalize or categorize the variables
populations['access_cat'] = pd.qcut(populations['accessibility'], 2, labels=['Low', 'High'])
populations['income_cat'] = pd.qcut(populations['PerCapitaI'], 2, labels=['Low', 'High'])
populations['insurance_cat'] = pd.qcut(populations['HI_block'], 2, labels=['Low', 'High'])
populations['age_cat'] = pd.qcut(populations['age_18to65'], 2, labels=['Low', 'High'])
populations['population_cat'] = pd.qcut(populations['Bl_totalpo'], 2, labels=['Low', 'High'])

# Create bivariate choropleth maps
def plot_bivariate_map(df, column1, column2, title):
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    df['bivariate'] = df[column1].astype(str) + '-' + df[column2].astype(str)
    df.plot(column='bivariate', cmap='YlOrRd', ax=ax, legend=True)
    ax.set_title(title)
    plt.show()

# Plot maps for each combination
plot_bivariate_map(populations, 'access_cat', 'income_cat', 'Accessibility and Income')
plt.show()

plot_bivariate_map(populations, 'access_cat', 'insurance_cat', 'Accessibility and Health Insurance')
plt.show()


plot_bivariate_map(populations, 'access_cat', 'age_cat', 'Accessibility and Age')
plt.show()

plot_bivariate_map(populations, 'access_cat', 'population_cat', 'Accessibility and Total Population')
plt.show()


neighbourhoods=gpd.read_file('/Users/ushashi/Documents/codes/Neighborhood_Clusters.shp').to_crs('epsg:26985')



# Step 1: Spatial join - assign each block to a neighborhood
blocks_with_neighborhoods = gpd.sjoin(populations, neighbourhoods, how='inner', predicate='intersects')

# Step 2: Group by neighborhood and calculate statistics
# Replace 'neighborhood_name' with the actual column name in your neighborhood file
neighborhood_scores = blocks_with_neighborhoods.groupby('NBH_NAMES').agg({
    'accessibility': 'mean',  # you can also use 'median', 'sum', etc.
    'Total Popu': 'sum'       # optional: to get total population per neighborhood
}).reset_index()

# Optional: merge scores back to neighborhood geometry
neighborhoods_final = neighbourhoods.merge(neighborhood_scores, on='NBH_NAMES')

print(neighborhoods_final)
neighborhoods_final.to_file('/Users/ushashi/Documents/codes/Neighbourhoods_dc.shp')
# Plotting the accessibility scores by neighborhood
fig, ax = plt.subplots(figsize=(12, 10))

# Replace 'weighted_accessibility' with 'accessibility' if you used the unweighted version
neighborhoods_final.plot(
    column='accessibility',    # or 'accessibility'
    cmap='RdYlBu',                     # Color map
    linewidth=0.5,
    edgecolor='white',
    legend=True,
    ax=ax
)




# Title and axes labels
ax.set_title('Neighborhood-level Accessibility to Intermediate Care Facilities in Washington DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=12)
ax.set_ylabel('Latitude', fontsize=12)

# Remove axes ticks
ax.set_xticks([])
ax.set_yticks([])

# Optional: annotate neighborhood names
# for idx, row in neighborhoods_final.iterrows():
#     plt.annotate(s=row['neighborhood_name'], xy=(row.geometry.centroid.x, row.geometry.centroid.y),
#                  horizontalalignment='center', fontsize=8, color='black')

plt.tight_layout()
plt.show()


