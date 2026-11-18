
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"

report = pd.read_csv(REPORT_DIR / "item_matching_report.csv")

# These require specification or sample confirmation.
REVIEW_TERMS = [
    "as per sample",
    "maintenance",
    "urgent",
    "repeat"
]

# Review low-scoring suggestions even if they appear plausible.
def classify(row):
    description = str(row["original_description"]).lower()
    score = float(row["similarity_score"])

    if any(term in description for term in REVIEW_TERMS):
        return "HUMAN_CONFIRMATION"

    if score >= 0.90:
        return "STRONG_MATCH_CANDIDATE"

    if score >= 0.60:
        return "HUMAN_CONFIRMATION"

    return "NEW_ITEM_OR_MATCH_REVIEW"

report["review_decision"] = report.apply(classify, axis=1)

output = REPORT_DIR / "matching_review.csv"
report.to_csv(output, index=False)

print("\nREVIEW DECISION SUMMARY")
print(report["review_decision"].value_counts())

print("\nRECORDS REQUIRING REVIEW")
print(
    report[
        report["review_decision"] != "STRONG_MATCH_CANDIDATE"
    ][
        [
            "pr_no",
            "original_description",
            "suggested_item_code",
            "suggested_description",
            "similarity_score",
            "review_decision"
        ]
    ].to_string(index=False)
)

print(f"\nSaved report: {output}")
    