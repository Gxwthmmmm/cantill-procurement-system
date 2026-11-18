# Backend

Run from this directory after creating `.env`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

Import the supplied CSVs:

```powershell
$env:PYTHONPATH = (Get-Location).Path
py -m scripts.import_task_data
py -m scripts.seed_policy
```
