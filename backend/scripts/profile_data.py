
from pathlib import Path
import pandas as pd

# Locate the data directory
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

print("=" * 70)
print("CANTILL PROCUREMENT - DATA PROFILING")
print("=" * 70)

csv_files = sorted(DATA_DIR.rglob("*.csv"))

if not csv_files:
    print("No CSV files found!")
    raise SystemExit(1)

for file_path in csv_files:

    print("\n" + "=" * 70)
    print(f"DATASET: {file_path.name}")
    print("=" * 70)

    try:
        df = pd.read_csv(file_path)

        # Dataset dimensions
        print(f"\nRows: {df.shape[0]}")
        print(f"Columns: {df.shape[1]}")

        # Column names and data types
        print("\nCOLUMN INFORMATION:")
        print(df.dtypes.to_string())

        # Missing values
        print("\nMISSING VALUES:")
        missing = df.isnull().sum()
        print(missing[missing > 0].to_string()
              if missing.any() else "No missing values")

        # Duplicate rows
        print("\nDUPLICATE ROWS:")
        print(df.duplicated().sum())

        # Sample records
        print("\nFIRST 3 RECORDS:")
        print(df.head(3).to_string(index=False))

    except Exception as error:
        print(f"Error processing {file_path.name}: {error}")

print("\n" + "=" * 70)
print("DATA PROFILING COMPLETED")
print("=" * 70)
