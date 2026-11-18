
from pathlib import Path
from difflib import SequenceMatcher
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUTPUT_DIR.mkdir(exist_ok=True)

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))
    if not matches:
        raise FileNotFoundError(filename)
    return pd.read_csv(matches[0])

prs = load_csv("sample_pr_batch.csv")
items = load_csv("item_master.csv")

missing = prs[prs["item_code"].isna()].copy()

def normalize(value):
    return (
        str(value).lower().strip()
        .replace("-", " ")
        .replace("/", " ")
    )

results = []

for _, pr in missing.iterrows():
    description = normalize(pr["description"])
    candidates = []

    for _, item in items.iterrows():
        master_description = normalize(item["description"])
        score = SequenceMatcher(
            None, description, master_description
        ).ratio()

        candidates.append({
            "item_code": item["item_code"],
            "master_description": item["description"],
            "score": score
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    if best["score"] >= 0.90:
        status = "AUTO_MATCH_CANDIDATE"
    elif best["score"] >= 0.60:
        status = "MANUAL_REVIEW"
    else:
        status = "NEW_ITEM_CANDIDATE"

    results.append({
        "pr_no": pr["pr_no"],
        "pr_line": pr["pr_line"],
        "original_description": pr["description"],
        "suggested_item_code": best["item_code"],
        "suggested_description": best["master_description"],
        "similarity_score": round(best["score"], 3),
        "matching_status": status
    })

report = pd.DataFrame(results)

output_file = OUTPUT_DIR / "item_matching_report.csv"
report.to_csv(output_file, index=False)

print("\nMATCHING REPORT SUMMARY")
print(report["matching_status"].value_counts())
print(f"\nReport saved to: {output_file}")
print("\nMANUAL REVIEW AND NEW ITEM CANDIDATES")
print(
    report[
        report["matching_status"].isin(
            ["MANUAL_REVIEW", "NEW_ITEM_CANDIDATE"]
        )
    ].to_string(index=False)
)