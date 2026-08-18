import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load world map data
world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))

# Load DC public schools data
schools = gpd.read_file('DC_Public_Schools.shp').to_crs('epsg:26985')

# Load population data from a CSV file
centroids = pd.read_csv('popu&centroid.csv')

# Create a Geopandas dataframe from the population data
centroids = gpd.GeoDataFrame(centroids, geometry=gpd.points_from_xy(centroids.Longitude, centroids.Latitude), crs='epsg:4326')

# Reproject the population data to match the schools data
centroids = centroids.to_crs('epsg:26985')

# Set constant scaling factor J
J = 1

# Set distance decay parameter for age
d0_age = 10000

# Define distance decay function for age
def age_decay(distance, d0=d0_age):
    return (np.exp(-0.5 * (distance/d0)**2) - np.exp(-0.5)) / (1 - np.exp(-0.5))

# Calculate age weights for each school
age_weights = {}

for idx, school in schools.iterrows():
    age_weights[idx] = { '<18': 0, '18to65': 0, '>65': 0 }

    # Calculate age weights for each census tract within distance threshold
    for i, tract in centroids.iterrows():
        distance = school.geometry.distance(tract.geometry)
        
        # Give weight to the population based on the distance between the origin and destination. the weights of the population are calculated for each census tract based on the diatnce btween each census tract and all the schools
        if distance <= 900: # Set distance threshold here
            age_weights[idx]['<18'] += tract['Total popu under 18'] * age_decay(distance)
            age_weights[idx]['18to65'] += tract['eighteento65'] * age_decay(distance)
            age_weights[idx]['>65'] += tract['65 years and over'] * age_decay(distance)

# Calculate accessibility for each census tract and school
accessibility = pd.DataFrame(index=centroids.index, columns=schools.index)

for j, school in schools.iterrows():
    age_weights_school = { '<18': 0, '18to65': 0, '>65': 0 }

    for i, tract in centroids.iterrows():
        # Calculate age weights for census tract
        distance = school.geometry.distance(tract.geometry)
        age_weights_school['<18'] = tract['Total popu under 18'] * age_decay(distance)
        age_weights_school['18to65'] = tract['eighteento65'] * age_decay(distance)
        age_weights_school['>65'] = tract['65 years and over'] * age_decay(distance)

        # Calculate accessibility for school and census tract
        supply = school['TOTAL_STUD']
        demand = sum(age_weights_school.values())
        if demand > 0:
            accessibility.at[i,j] = J * supply * age_decay(distance) / demand
        else:
            accessibility.at[i,j] = 0

print(accessibility)

centroids['accessibility'] = accessibility.sum(axis=1)

centroids = centroids.drop(centroids.index[-1])

fig, ax = plt.subplots(figsize=(12, 10))

# plot census tracts with accessibility values
centroids.join(accessibility).plot(column='accessibility', cmap='coolwarm', linewidth=0.5, edgecolor='white', legend=True, ax=ax)

# plot schools on the map
schools.plot(ax=ax, color='black', markersize=5)

# set axis labels and title

ax.set_title('Accessibility map of DC', fontsize=16)
ax.set_xlabel('Longitude', fontsize=14)
ax.set_ylabel('Latitude', fontsize=14)

plt.show()
