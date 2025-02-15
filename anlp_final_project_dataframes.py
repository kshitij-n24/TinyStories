# -*- coding: utf-8 -*-
"""ANLP Final Project Dataframes

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/#fileId=https%3A//storage.googleapis.com/kaggle-colab-exported-notebooks/anlp-final-project-dataframes-e00c861b-ed97-4757-92a7-6625d84c5163.ipynb%3FX-Goog-Algorithm%3DGOOG4-RSA-SHA256%26X-Goog-Credential%3Dgcp-kaggle-com%2540kaggle-161607.iam.gserviceaccount.com/20241120/auto/storage/goog4_request%26X-Goog-Date%3D20241120T225540Z%26X-Goog-Expires%3D259200%26X-Goog-SignedHeaders%3Dhost%26X-Goog-Signature%3D6cf1356aa0d871768a617b22c5288d87a6eb97de74897df8fdb7b0d7d81d61a4aeebdf6f1ba85eea5b18b5247f09ff0dac995035b2462accd0d3ba1c0cc4b7be2430cfe7199b63c50ad05b2b2b1fde67d2afa56ecee33a8f98843a1b11173d066fc3351bf5d0d79f448937325dccce854d05704dfb18362cc5b50dc93d7d6d9b908096b6549a5ce9670094ee9e2be3ee9fe8bd2224e6887c54b364a25676e2fd4800764576ab525a3dd8b70983903ce4c47cca9e8a64e635fb1b39f3d55ffc7b7018ca1994572aaeab349f5f2ba7cc388e99d62ec20343525e2feb32c351006cb7ab4bff177bdb0b23b6367d5375989ded3ad94cc3ef6336f55489386fcfb9ad
"""

# IMPORTANT: SOME KAGGLE DATA SOURCES ARE PRIVATE
# RUN THIS CELL IN ORDER TO IMPORT YOUR KAGGLE DATA SOURCES.
import kagglehub
kagglehub.login()

# IMPORTANT: RUN THIS CELL IN ORDER TO IMPORT YOUR KAGGLE DATA SOURCES,
# THEN FEEL FREE TO DELETE THIS CELL.
# NOTE: THIS NOTEBOOK ENVIRONMENT DIFFERS FROM KAGGLE'S PYTHON
# ENVIRONMENT SO THERE MAY BE MISSING LIBRARIES USED BY YOUR
# NOTEBOOK.

cyclewhiz4488_compare_df_v4_path = kagglehub.dataset_download('cyclewhiz4488/compare-df-v4')
cyclewhiz4488_compare_pkls_path = kagglehub.dataset_download('cyclewhiz4488/compare-pkls')

print('Data source import complete.')

"""# Imports"""

import os
import numpy as np
from math import pi
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import ttest_rel

"""# Loading the Dataframes"""

def load_dataframe(df_path):
    if os.path.exists(df_path):
        df = pd.read_pickle(df_path)
        print("Loaded dataframe!")
    elif not os.path.exists(df_path):
        print("Result directory not found! Please check the path.")

    return df

score_list = []

df = pd.DataFrame(score_list, columns=["Input Prompt", "Grammar", "Creativity", "Consistency", "Age Group"])

baseline_dfpath = '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-2-2.'
custom_dfpath = '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-4-2.pkl'

df_baseline = load_dataframe(baseline_dfpath)

df_baseline

df_custom = load_dataframe(custom_dfpath)

df_custom

df_baseline['Age Group'] = df_baseline['Age Group'].apply(lambda x: x.split()[0] if '(' in x else x)
df_custom['Age Group'] = df_custom['Age Group'].apply(lambda x: x.split()[0] if '(' in x else x)

df_baseline

df_custom = df_custom.iloc[100:200].reset_index(drop=True)
df_custom

"""# Average Scores by Criteria"""

# Calculate mean and standard deviation for both models
baseline_means = df_baseline[["Grammar", "Creativity", "Consistency"]].mean()
custom_means = df_custom[["Grammar", "Creativity", "Consistency"]].mean()

baseline_std = df_baseline[["Grammar", "Creativity", "Consistency"]].std()
custom_std = df_custom[["Grammar", "Creativity", "Consistency"]].std()

# Display means and standard deviations for easy comparison
comparison_df = pd.DataFrame({
    "Baseline Mean": baseline_means,
    "Custom Model Mean": custom_means,
    "Baseline Std Dev": baseline_std,
    "Custom Model Std Dev": custom_std
})
print(comparison_df)

"""# Statistical Tests"""

# Perform paired t-tests for each criterion
for criterion in ["Grammar", "Creativity", "Consistency"]:
    t_stat, p_val = ttest_rel(df_baseline[criterion], df_custom[criterion])
    print(f"{criterion} - t-statistic: {t_stat}, p-value: {p_val}")

"""# Age Group Distribution"""

# Count occurrences of each age group in both dataframes
age_group_baseline = df_baseline["Age Group"].value_counts(normalize=True)
age_group_custom = df_custom["Age Group"].value_counts(normalize=True)

# Combine into a single DataFrame for easier comparison
age_group_df = pd.DataFrame({
    "Baseline": age_group_baseline,
    "Custom Model": age_group_custom
}).fillna(0)
print(age_group_df)

"""# Plots

## Bar Plot of Mean Scores
"""

criteria = ["Grammar", "Creativity", "Consistency"]
x = np.arange(len(criteria))
width = 0.35

fig, ax = plt.subplots()
ax.bar(x - width/2, baseline_means, width, label='Baseline', yerr=baseline_std)
ax.bar(x + width/2, custom_means, width, label='Custom Model', yerr=custom_std)

ax.set_ylabel('Average Scores')
ax.set_title('Comparison of Model Scores by Criterion')
ax.set_xticks(x)
ax.set_xticklabels(criteria)
ax.legend()

plt.show()

"""## Box Plots for Score Distributions"""

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for i, criterion in enumerate(criteria):
    axes[i].boxplot([df_baseline[criterion], df_custom[criterion]], labels=['Baseline', 'Custom Model'])
    axes[i].set_title(f'Distribution of {criterion} Scores')
plt.tight_layout()
plt.show()

"""## Stacked Bar Plot for Age Group Distribution"""

age_group_df.plot(kind="bar", stacked=False)
plt.title("Age Group Distribution Comparison")
plt.ylabel("Proportion")
plt.show()

"""## Radar Chart"""

labels = criteria
baseline_values = baseline_means.values
custom_values = custom_means.values

angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
angles += angles[:1]

baseline_values = np.concatenate((baseline_values, [baseline_values[0]]))
custom_values = np.concatenate((custom_values, [custom_values[0]]))

fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
ax.fill(angles, baseline_values, color='red', alpha=0.25)
ax.fill(angles, custom_values, color='blue', alpha=0.25)
ax.set_yticklabels([])
ax.set_xticks(angles[:-1])
ax.set_xticklabels(labels)

plt.title("Radar Chart Comparison of Criteria")
plt.show()

import os
import numpy as np
from math import pi
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import ttest_rel


def load_dataframe(df_path):
    if os.path.exists(df_path):
        df = pd.read_pickle(df_path)
        print(f"Loaded dataframe from {df_path}!")
        return df
    else:
        print(f"Result directory not found for path: {df_path}")
        return None


# Define paths for the dataframes
df_paths = [
    '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-2-2.pkl',
    '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-4-2.pkl',
    '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-4-4.pkl',
    '/kaggle/input/compare-pkls/PKL_Files/8M_Files/Hyperparameter_Tuning_Files/rating_df_custom-8M-8-8.pkl'
]

# Load the dataframes
dataframes = [load_dataframe(path) for path in df_paths]
dataframes = [df for df in dataframes if df is not None]

# Ensure all dataframes are loaded
if len(dataframes) < len(df_paths):
    print("Not all dataframes could be loaded. Exiting.")
    exit()

criteria = ["Grammar", "Creativity", "Consistency"]
age_group_column = "Age Group"

# Calculate mean and standard deviation for all models
stats = {
    "Mean": [df[criteria].mean() for df in dataframes],
    "Std Dev": [df[criteria].std() for df in dataframes],
}

comparison_df = pd.concat(stats["Mean"], axis=1)
comparison_df.columns = [f"Model {i+1} Mean" for i in range(len(dataframes))]

std_df = pd.concat(stats["Std Dev"], axis=1)
std_df.columns = [f"Model {i+1} Std Dev" for i in range(len(dataframes))]

print("Comparison of Means:")
print(comparison_df)
print("\nComparison of Standard Deviations:")
print(std_df)

# Perform paired t-tests for each pair of models
print("\nPaired T-tests:")
for i in range(len(dataframes)):
    for j in range(i + 1, len(dataframes)):
        print(f"\nModel {i+1} vs Model {j+1}")
        for criterion in criteria:
            t_stat, p_val = ttest_rel(dataframes[i][criterion], dataframes[j][criterion])
            print(f"{criterion} - t-statistic: {t_stat:.3f}, p-value: {p_val:.3f}")

# Count occurrences of each age group in all dataframes
age_group_counts = [df[age_group_column].value_counts(normalize=True) for df in dataframes]
age_group_df = pd.concat(age_group_counts, axis=1).fillna(0)
age_group_df.columns = [f"Model {i+1}" for i in range(len(dataframes))]
print("\nAge Group Distribution:")
print(age_group_df)

# Bar chart comparison
x = np.arange(len(criteria))
width = 0.2

fig, ax = plt.subplots()
for i, (means, std_dev) in enumerate(zip(stats["Mean"], stats["Std Dev"])):
    ax.bar(x + i * width - width * (len(dataframes) - 1) / 2, means, width, label=f'Model {i+1}', yerr=std_dev)

ax.set_ylabel('Average Scores')
ax.set_title('Comparison of Model Scores by Criterion')
ax.set_xticks(x)
ax.set_xticklabels(criteria)
ax.legend()

plt.show()

# Boxplots for each criterion
fig, axes = plt.subplots(1, len(criteria), figsize=(5 * len(criteria), 5))
for i, criterion in enumerate(criteria):
    axes[i].boxplot([df[criterion] for df in dataframes], labels=[f'Model {j+1}' for j in range(len(dataframes))])
    axes[i].set_title(f'Distribution of {criterion} Scores')
plt.tight_layout()
plt.show()

# Age group comparison
age_group_df.plot(kind="bar", stacked=False)
plt.title("Age Group Distribution Comparison")
plt.ylabel("Proportion")
plt.show()

# Radar chart
angles = np.linspace(0, 2 * np.pi, len(criteria), endpoint=False).tolist()
angles += angles[:1]

fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
for i, means in enumerate(stats["Mean"]):
    values = np.concatenate((means.values, [means.values[0]]))
    ax.fill(angles, values, alpha=0.25, label=f'Model {i+1}')
    ax.plot(angles, values)

ax.set_yticklabels([])
ax.set_xticks(angles[:-1])
ax.set_xticklabels(criteria)
plt.legend()
plt.title("Radar Chart Comparison of Criteria")
plt.show()

