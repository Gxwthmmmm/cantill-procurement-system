from pathlib import Path
from app.db.session import SessionLocal
from app.services.importer import import_all_source_data
from app.core.config import settings

def main():
    db=SessionLocal()
    try:
        counts=import_all_source_data(db, Path(settings.source_data_dir))
        for dataset,count in counts.items(): print(f"{dataset}: {count}")
        print(f"TOTAL: {sum(counts.values())}")
    finally: db.close()

if __name__=="__main__": main()
