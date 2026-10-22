"""Preserve any journal/calibration from the initial, project-local release."""
from pathlib import Path
import shutil
import sqlite3

root = Path(__file__).resolve().parent.parent
seed = root/'build-assets'/'initial-data'
journal = root/'runs'/'journal.sqlite3'
if journal.exists():
    target = seed/'runs'/'journal.sqlite3'
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(journal) as source, sqlite3.connect(target) as destination:
        source.backup(destination)
profile = root/'calibration'/'profile.json'
if profile.exists():
    target = seed/'calibration'/'profile.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(profile, target)
