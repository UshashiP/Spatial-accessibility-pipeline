##code working fine for lorenze cureve and gini coefficent comparison"
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import pandas as pd

# Load the datasets
advanced_2sfca_df = pd.read_csv('access_ICF_final.csv')
original_2sfca_df = pd.read_csv('original_2sfca.csv')


# Extract accessibility values
advanced_accessibility = advanced_2sfca_df['accessibility'].values
original_accessibility = original_2sfca_df['Accessibility'].values

# Function to calculate Gini coefficient
def gini_coefficient(x):
    # Mean absolute difference
    mad = np.abs(np.subtract.outer(x, x)).mean()
    # Relative mean absolute difference
    rmad = mad / np.mean(x)
    # Gini coefficient
    return 0.5 * rmad

# Function to plot Lorenz curve
def plot_lorenz_curve(data, label):
    data_sorted = np.sort(data)
    data_cum = np.cumsum(data_sorted) / np.sum(data_sorted)
    data_cum = np.insert(data_cum, 0, 0)
    plt.plot(np.linspace(0, 1, len(data_cum)), data_cum, label=label)

# Calculating Gini coefficients
gini_advanced = gini_coefficient(advanced_accessibility)
gini_original = gini_coefficient(original_accessibility)

# Plotting Lorenz curves
plt.figure(figsize=(10, 6))
plot_lorenz_curve(advanced_accessibility, f'Advanced 2SFCA (Gini: {gini_advanced:.4f})')
plot_lorenz_curve(original_accessibility, f'Original 2SFCA (Gini: {gini_original:.4f})')

# Plotting the equality line
plt.plot([0, 1], [0, 1], color='black', linestyle='--', label='Equality Line')

# Final plot adjustments
plt.title('Lorenz Curve Comparison of Accessibility Measures')
plt.xlabel('Cumulative Share of Population')
plt.ylabel('Cumulative Share of Accessibility')
plt.legend()
plt.grid(True)

# Save the plot
plt.savefig('lorenz_curve_comparison.png', dpi=300)  # Save as PNG with 300 dpi resolution

# Display the plot
plt.show()

# Save the Gini coefficients to a text file
with open('gini_coefficients.txt', 'w') as f:
    f.write(f"Gini Coefficient for Advanced 2SFCA: {gini_advanced}\n")
    f.write(f"Gini Coefficient for Original 2SFCA: {gini_original}\n")
