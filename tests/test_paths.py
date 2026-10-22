from pathlib import Path
import sqlite3
from royalty_entry import paths


def test_data_is_outside_the_executable_folder(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
    assert paths.data_root() == tmp_path/'local'/'RoyaltyEntry'


def test_initial_upgrade_preserves_journal_and_does_not_overwrite_new_data(monkeypatch, tmp_path):
    legacy = tmp_path/'old'
    destination = tmp_path/'appdata'
    (legacy/'runs').mkdir(parents=True)
    (legacy/'calibration').mkdir()
    source_path = legacy/'runs'/'journal.sqlite3'
    with sqlite3.connect(source_path) as db:
        db.execute('CREATE TABLE saved (license TEXT)')
        db.execute("INSERT INTO saved VALUES ('123')")
    (legacy/'calibration'/'profile.json').write_text('{"version":1}', encoding='utf-8')
    monkeypatch.setattr(paths, 'asset_root', lambda: legacy)
    monkeypatch.setattr(paths, 'data_root', lambda: destination)
    paths.initialize_data()
    with sqlite3.connect(destination/'runs'/'journal.sqlite3') as db:
        assert db.execute('SELECT license FROM saved').fetchall() == [('123',)]
        db.execute("INSERT INTO saved VALUES ('456')")
    paths.initialize_data()
    with sqlite3.connect(destination/'runs'/'journal.sqlite3') as db:
        assert db.execute('SELECT license FROM saved').fetchall() == [('123',), ('456',)]
    assert (destination/'calibration'/'profile.json').read_text(encoding='utf-8') == '{"version":1}'
