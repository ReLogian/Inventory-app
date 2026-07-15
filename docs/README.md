# Inventory Management App

Simple Python + Tkinter inventory system with SQLite backend.

## Features
- Add / remove stock
- Product management
- Search, category filtering & sorting
- Edit and delete products
- CSV import / export
- Daily and monthly sales summaries

## Run
```bash
python src/inventorymgmt.py
```

## Windows Portable Bundle
Use `run_inventory.bat` to start the app on Windows.

For a fully portable folder, place a Windows Python runtime in `python/` and PortableGit in `PortableGit/`, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_bundle.ps1 -PythonDir C:\path\to\python -PortableGitDir C:\path\to\PortableGit
```

The app checks Git for updates on startup. When an update is available, it asks before running `git pull --ff-only`.
