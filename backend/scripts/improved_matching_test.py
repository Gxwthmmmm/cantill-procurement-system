
from pathlib import Path
from difflib import SequenceMatcher
import pandas as pd
import re

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))
    if not matches:
        raise FileNotFoundError(filename)
    return pd.read_csv(matches[0])

def normalize(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.split()

# Diagnostic-only abbreviation expansion
ABBREVIATIONS = {
    "brg": "bearing",
    "pneu": "pneumatic",
    "hyd": "hydraulic",
    "eot": "eot",
}

def expand_tokens(tokens):
    return [ABBREVIATIONS.get(token, token) for token in tokens]

def token_score(a, b):
    a_tokens = set(expand_tokens(normalize(a)))
    b_tokens = set(expand_tokens(normalize(b)))

    if not a_tokens or not b_tokens:
        return 0

    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)

prs = load_csv("sample_pr_batch.csv")
items = load_csv("item_master.csv")

missing = prs[prs["item_code"].isna()]

print("=" * 75)
print("IMPROVED DESCRIPTION MATCHING - DIAGNOSTIC")
print("=" * 75)

for _, pr in missing.iterrows():
    candidates = []

    for _, item in items.iterrows():
        char_score = SequenceMatcher(
            None,
            " ".join(normalize(pr["description"])),
            " ".join(normalize(item["description"]))
        ).ratio()

        tokens = token_score(
            pr["description"],
            item["description"]
        )

        combined_score = 0.5 * char_score + 0.5 * tokens

        candidates.append({
            "code": item["item_code"],
            "description": item["description"],
            "char_score": char_score,
            "token_score": tokens,
            "combined_score": combined_score
        })

    candidates.sort(
        key=lambda x: x["combined_score"],
        reverse=True
    )

    best = candidates[0]

    print(f"\n{pr['pr_no']} | {pr['description']}")
    print(
        f"  {best['code']} | {best['description']} "
        f"| Combined score: {best['combined_score']:.3f}"
    )

print("\nDIAGNOSTIC COMPLETED")
