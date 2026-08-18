
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Load DC public schools data
schools = gpd.read_file('Intermediate_Care_Facilities.shp').to_crs('epsg:26985')
pd.set_option('display.max_columns', None)

# Load population data
populations = gpd.read_file('blocksandtract_economic_final.shp').to_crs('epsg:26985')


populations['Total Popu']= populations['Total Popu'].fillna(0)
populations['PerCapitaI']= populations['PerCapitaI'].fillna(0)
populations['HI_block']= populations['HI_block'].fillna(0)
populations['age_18to65'] = populations['age_18to65'].fillna(0)

# Normalize the additional variables
populations['Total Popu'] = (populations['Total Popu'] - populations['Total Popu'].min()) / (populations['Total Popu'].max() - populations['Total Popu'].min())
populations['PerCapitaI'] = (populations['PerCapitaI'] - populations['PerCapitaI'].min()) /(populations['PerCapitaI'].max() - populations['PerCapitaI'].min())
populations['HI_block'] = (populations['HI_block'] - populations['HI_block'].min()) / (populations['HI_block'].max() - populations['HI_block'].min())
populations['age_18to65'] = (populations['age_18to65'] - populations['age_18to65'].min()) /(populations['age_18to65'].max() - populations['age_18to65'].min())

#print(populations)
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
    valid_blocks = populations.iloc[valid_indices[0]]
    
# Create a new GeoDataFrame for the valid blocks
#valid_blocks_gdf = gpd.GeoDataFrame(valid_blocks, geometry=valid_blocks.geometry)


# Print information for each block
# Print information for each block
# Print information for each block
for idx, block in valid_blocks.items():
    print(f"{idx}: {block}")

from shapely.geometry import Point
import geopandas as gpd

# Assuming `schools` is your GeoDataFrame containing school locations
# and `blocks` is your GeoDataFrame containing block information

# Create a buffer around each school representing the 900m distance
schools_buffered = schools.copy()
schools_buffered['geometry'] = schools_buffered.buffer(900)

# Iterate over each school and find blocks within the buffer
blocks_within_900m = gpd.GeoDataFrame()
for idx, school in schools_buffered.iterrows():
    # Create a temporary GeoDataFrame with only the blocks within the buffer
    blocks_within_buffer = populations[populations.centroid.within(school.geometry)]
    blocks_within_900m = pd.concat([blocks_within_900m, blocks_within_buffer], ignore_index=True)
pd.set_option('display.max_columns', None)

print(len(blocks_within_900m))
# Now, `blocks_within_900m` contains all the blocks within 900m of any school
import geopandas as gpd
import matplotlib.pyplot as plt

# Assuming `blocks_within_900m_unique` contains the GeoDataFrame of unique blocks within 900m

# Plot the blocks
fig, ax = plt.subplots(figsize=(12, 10))
blocks_within_900m.plot(ax=ax, color='blue', alpha=0.5)

# Plot the schools on the same map
schools.plot(ax=ax, color='red', markersize=5)

# Set axis labels and title
ax.set_title('Blocks within 900m of Schools', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

# Show the map
plt.show()

  
  