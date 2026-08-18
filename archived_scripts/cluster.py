import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import numpy as np

df = pd.read_csv('access_ICF_final.csv')

# Define thresholds for income and accessibility (these can be adjusted as needed)
income_thresholds = np.quantile(df['Bl_incomep'].dropna(), [0.33, 0.66])
accessibility_thresholds = np.quantile(df['accessibility'].dropna(), [0.33, 0.66])

# Define the categories based on the thresholds
df['income_category'] = pd.cut(df['Bl_incomep'], bins=[-np.inf, income_thresholds[0], income_thresholds[1], np.inf], labels=['Low', 'Medium', 'High'])
df['accessibility_category'] = pd.cut(df['accessibility'], bins=[-np.inf, accessibility_thresholds[0], accessibility_thresholds[1], np.inf], labels=['Low', 'Medium', 'High'])

# Define age categories (assuming 'age_18to65' represents the age group 18 to 65)
df['age_category'] = pd.cut(df['age_18to65'], bins=[0, 18, 65, 100], labels=['Youth', 'Adult', 'Senior'])

# Print the head to check new columns
df.head()