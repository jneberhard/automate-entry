"""Separate bundled read-only assets from durable, per-user application data."""
import os
from pathlib import Path
import shutil
import sqlite3
import sys


def asset_root():
    return Path(__file__).resolve().parent.parent


def data_root():
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        raise RuntimeError('Windows LOCALAPPDATA is unavailable; cannot locate application data')
    return Path(base) / 'RoyaltyEntry'


def initialize_data():
    destination = data_root()
    destination.mkdir(parents=True, exist_ok=True)
    # Upgrade the original source version without discarding its duplicate-payment journal.
    legacy = asset_root() / ('initial-data' if getattr(sys, 'frozen', False) else '')
    source_journal = legacy / 'runs' / 'journal.sqlite3'
    target_journal = destination / 'runs' / 'journal.sqlite3'
    if source_journal.exists() and not target_journal.exists():
        target_journal.parent.mkdir(exist_ok=True)
        with sqlite3.connect(source_journal) as source, sqlite3.connect(target_journal) as target:
            source.backup(target)
    source_profile = legacy / 'calibration' / 'profile.json'
    target_profile = destination / 'calibration' / 'profile.json'
    if source_profile.exists() and not target_profile.exists():
        target_profile.parent.mkdir(exist_ok=True)
        shutil.copy2(source_profile, target_profile)
    return destination
