
from pathlib import Path
import pandas as pd
from difflib import SequenceMatcher

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))
    if not matches:
        raise FileNotFoundError(filename)
    return pd.read_csv(matches[0])

prs = load_csv("sample_pr_batch.csv")
items = load_csv("item_master.csv")

missing = prs[prs["item_code"].isna()].copy()

def normalize(value):
    return str(value).lower().strip().replace("-", " ").replace("/", " ")

print("=" * 75)
print("DESCRIPTION-BASED ITEM MATCHING INVESTIGATION")
print("=" * 75)

for _, pr in missing.iterrows():
    description = normalize(pr["description"])

    scores = []

    for _, item in items.iterrows():
        master_description = normalize(item["description"])
        score = SequenceMatcher(
            None, description, master_description
        ).ratio()

        scores.append((score, item["item_code"], item["description"]))

    scores.sort(reverse=True)

    print(f"\nPR: {pr['pr_no']} | {pr['description']}")
    for score, code, master_desc in scores[:3]:
        print(f"  {score:.2f} | {code} | {master_desc}")

print("\nINVESTIGATION COMPLETED")
