
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load accessibility scores from separate files
# Replace 'file_path' with the actual file paths for each method
hansen_df = pd.read_csv('access_ICF_hansen.csv')
gravity_df = pd.read_csv('original_2sfca.csv')
cumulative_df = pd.read_csv('access_ICF_cumulative_opportunity.csv')
advanced_df = pd.read_csv('access_ICF_final.csv')


# Ensure that all accessibility scores are numeric, converting where necessary
hansen_scores = pd.to_numeric(hansen_df['hansen_accessibility'], errors='coerce').fillna(0)
gravity_scores = pd.to_numeric(gravity_df['Accessibil'], errors='coerce').fillna(0)
cumulative_scores = pd.to_numeric(cumulative_df['cumulative_opportunity'], errors='coerce').fillna(0)
advanced_scores = pd.to_numeric(advanced_df['accessibility'], errors='coerce').fillna(0)

# Define Gini coefficient function
def gini_coefficient(x):
    """Calculate the Gini coefficient of a numpy array."""
    x = np.sort(x)  # Sort the values
    n = len(x)
    cumulative_sum = np.cumsum(x)
    relative_mean_difference = (np.sum((2 * np.arange(1, n + 1) - n - 1) * x)) / (n * np.sum(x))
    return relative_mean_difference

# Define Lorenz curve plotting function
def plot_lorenz_curve(data, label):
    data_sorted = np.sort(data)
    data_cum = np.cumsum(data_sorted) / np.sum(data_sorted)
    data_cum = np.insert(data_cum, 0, 0)
    plt.plot(np.linspace(0, 1, len(data_cum)), data_cum, label=label)

# Recalculating Gini coefficients and plotting Lorenz curves with cleaned data
gini_hansen = gini_coefficient(hansen_scores)
gini_gravity = gini_coefficient(gravity_scores)
gini_cumulative = gini_coefficient(cumulative_scores)
gini_advanced = gini_coefficient(advanced_scores)

plt.figure(figsize=(10, 6))
plot_lorenz_curve(hansen_scores, f'Hansen Method (Gini: {gini_hansen:.4f})')
plot_lorenz_curve(gravity_scores, f'Gravity Method (Gini: {gini_gravity:.4f})')
plot_lorenz_curve(cumulative_scores, f'Cumulative Opportunity (Gini: {gini_cumulative:.4f})')
plot_lorenz_curve(advanced_scores, f'Advanced Method (Gini: {gini_advanced:.4f})')

# Plot the equality line
plt.plot([0, 1], [0, 1], color='black', linestyle='--', label='Equality Line')

# Final plot adjustments
plt.title('Lorenz Curve Comparison of Accessibility Methods')
plt.xlabel('Cumulative Share of Population')
plt.ylabel('Cumulative Share of Accessibility')
plt.legend()
plt.grid(True)
plt.show()

# Output Gini coefficients
gini_results = {
    "Hansen Method": gini_hansen,
    "Gravity Method": gini_gravity,
    "Cumulative Opportunity": gini_cumulative,
    "Advanced Method": gini_advanced
}

print(gini_results)
