import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib.pyplot as plt
import numpy as np

# Load your dataset (make sure all necessary columns are included)
data = pd.read_csv('access_ICF_final.csv')

# Selecting features and target
features = data[['Bl_totalpo', 'PerCapitaI', 'HI_block', 'eighteento', '65 years a']]
target = data['accessibility']  # Replace 'accessibility' wi

# Adding interaction terms between income and health insurance
features['Income_Health_Interaction'] = features['PerCapitaI'] * features['HI_block']

# Adding a log-transformed version of income
features['Log_Income'] = np.log1p(features['PerCapitaI'])

# If you have other ideas for feature engineering, you can add them here.
# Splitting the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.3, random_state=42)

# Define the parameter grid
param_grid = {
    'n_estimators': [100, 200, 300],  # Number of trees
    'max_depth': [None, 10, 20, 30],  # Maximum depth of the tree
    'min_samples_split': [2, 5, 10],  # Minimum number of samples required to split a node
    'min_samples_leaf': [1, 2, 4],    # Minimum number of samples required at each leaf node
    'bootstrap': [True, False]        # Whether bootstrap samples are used when building trees
}

# Initialize the Random Forest Regressor
rf = RandomForestRegressor(random_state=42)

# Perform GridSearchCV
grid_search = GridSearchCV(estimator=rf, param_grid=param_grid,
                           cv=3, n_jobs=-1, verbose=2, scoring='r2')

# Fit the model
grid_search.fit(X_train, y_train)

# Best parameters from grid search
best_params = grid_search.best_params_
print(f"Best Parameters: {best_params}")

# Use the best model to predict and evaluate
best_rf = grid_search.best_estimator_
y_pred_best = best_rf.predict(X_test)

# Evaluate the best model
mse_best = mean_squared_error(y_test, y_pred_best)
r2_best = r2_score(y_test, y_pred_best)

print(f'Optimized Mean Squared Error: {mse_best}')
print(f'Optimized R^2 Score: {r2_best}')



