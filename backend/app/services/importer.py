import csv
from pathlib import Path
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.models import SourceRecord

DATASETS = {
    "item_master": ("master_data/item_master.csv", "item_code"),
    "supplier_master": ("master_data/supplier_master.csv", "supplier_id"),
    "po_history": ("master_data/po_history.csv", "po_number"),
    "plants": ("master_data/plants.csv", "plant"),
    "contract_register": ("contracts/contract_register.csv", "contract_id"),
    "contract_lines": ("contracts/contract_lines.csv", "contract_id:item_code"),
    "sample_pr_batch": ("pr_batches/sample_pr_batch.csv", "pr_no:pr_line"),
}

def import_all_source_data(db: Session, source_dir: Path) -> dict[str, int]:
    """Idempotently replace the staged source records from the supplied task-kit CSVs."""
    counts: dict[str, int] = {}
    for dataset, (relative_path, key_fields) in DATASETS.items():
        path = source_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Required task-kit CSV not found: {path}")
        db.execute(delete(SourceRecord).where(SourceRecord.dataset == dataset))
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                keys = key_fields.split(":")
                record_key = "|".join((row.get(key) or "") for key in keys)
                db.add(SourceRecord(dataset=dataset, record_key=record_key, payload=row))
                counts[dataset] = counts.get(dataset, 0) + 1
    db.commit()
    return counts
