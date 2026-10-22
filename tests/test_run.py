import csv
import shutil
from decimal import Decimal
from threading import Event
from openpyxl import Workbook
import pytest
from royalty_entry.engine import run, RunLock
from royalty_entry.journal import Journal
from royalty_entry.rules import Record


def test_live_run_preserves_partial_removals_and_source_after_failure(tmp_path, monkeypatch):
    source = tmp_path/'source.xlsx'
    book = Workbook()
    sheet = book.active
    sheet.title = 'Payments'
    sheet['H1'], sheet['I1'] = 'Publisher', 'License'
    for row, license_number in [(2, '123'), (3, '123'), (4, '456')]:
        sheet.cell(row, 8, 'Publisher')
        sheet.cell(row, 9, license_number)
    book.save(source)
    original = source.read_bytes()
    exports = []

    def export(self, destination, remove_rows, use_excel=False):
        exports.append((set(remove_rows), use_excel))
        shutil.copy2(self.path, destination)

    monkeypatch.setattr('royalty_entry.workbook.Workbook.save_filtered', export)

    class InterruptedDriver:
        def open_record(self, record):
            if record.license == '456':
                raise RuntimeError('RDP disconnected')
            return True

        def details(self):
            return Decimal('-.02')

        def close_record(self):
            pass

    with pytest.raises(RuntimeError, match='RDP disconnected'):
        run(source, 'Payments', 2, 'Q3', True, tmp_path/'runs', InterruptedDriver, Event(), lambda _: None)
    assert exports == [(set(), True), ({2, 3}, False)]
    assert source.read_bytes() == original
    report = next((tmp_path/'runs').glob('*/report.csv'))
    with report.open(encoding='utf-8-sig', newline='') as file:
        statuses = [row[3] for row in list(csv.reader(file))[1:]]
    assert statuses == ['remove_balance', 'duplicate', 'STOPPED']
    journal = Journal(tmp_path/'runs'/'journal.sqlite3')
    assert journal.get(Record(2, '123', 'Publisher'), 'Q3')[0] == 'remove_balance'
    journal.close()


def test_run_lock_excludes_second_runner_and_releases(tmp_path):
    path = tmp_path/'run.lock'
    with RunLock(path):
        with pytest.raises(RuntimeError, match='Another royalty-entry run'):
            with RunLock(path):
                pytest.fail('Second run acquired the same lock')
    with RunLock(path):
        pass
