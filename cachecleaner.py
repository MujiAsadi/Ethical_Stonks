import os
import re
import pandas as pd

CACHE_FILE = 'ticker_grades_cache.csv'

def clean_cache_refusals(file_path):
    if not os.path.exists(file_path):
        print(f"Error: Could not find '{file_path}'.")
        return

    # Load cache
    df = pd.read_csv(file_path)
    initial_count = len(df)

    # Regex pattern to match typical AI refusal openings
    refusal_pattern = r'^(I cannot|I can\'t|I am unable|Sorry|As an AI)'

    # Identify rows that start with refusal phrases
    is_refusal = df['ethical_grade'].astype(str).str.strip().str.contains(
        refusal_pattern, flags=re.IGNORECASE, regex=True, na=False
    )

    # Filter out refusal rows
    df_clean = df[~is_refusal]
    removed_count = initial_count - len(df_clean)

    # Overwrite the CSV with cleaned data
    df_clean.to_csv(file_path, index=False)

    print(f"Cleanup Complete:")
    print(f" - Initial rows: {initial_count}")
    print(f" - Refusals removed: {removed_count}")
    print(f" - Valid grades remaining: {len(df_clean)}")

if __name__ == '__main__':
    clean_cache_refusals(CACHE_FILE)