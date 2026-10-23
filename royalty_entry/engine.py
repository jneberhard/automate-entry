import csv
from datetime import datetime
from pathlib import Path
import os
from .desktop import Cancelled
from .journal import Journal
from .rules import CENT, royalty_amount
from .workbook import Workbook


class RunLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        import msvcrt
        self.file = open(self.path, 'a+b')
        if os.fstat(self.file.fileno()).st_size == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise RuntimeError('Another royalty-entry run is active')
        return self

    def __exit__(self, *args):
        import msvcrt
        self.file.seek(0)
        msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()


def process_records(records, driver, reference, journal, live, report, stop):
    """Decision engine, independent of Excel and screen input for testing."""
    removed, outcomes = set(), {}
    for record in records:
        if stop.is_set():
            raise Cancelled('Stopped between rows')
        if record.key in outcomes:
            status = outcomes[record.key]
            if status.startswith('remove_'):
                removed.add(record.row)
            report(record, 'duplicate', '', f'Skipped repeated license/publisher; first outcome: {status}')
            continue
        previous = journal.get(record, reference)
        if previous and previous[0] == 'pending':
            raise RuntimeError(f'{record.license} / {record.publisher} has an unfinished save in the journal. Inspect it in License Manager before retrying. No automatic retry is allowed.')
        if previous and previous[0] == 'paid':
            outcomes[record.key] = 'already_paid'
            report(record, 'already_paid', previous[1], 'Previously completed by this program with this reference')
            continue
        if previous and previous[0].startswith('remove_'):
            status = previous[0]
            removed.add(record.row)
            outcomes[record.key] = status
            report(record, status, '', previous[2])
            continue
        if not driver.open_record(record):
            outcomes[record.key] = 'review'
            report(record, 'review', '', 'No exact license/publisher match; row retained')
            continue
        balance = driver.details()
        if balance < -CENT:
            status = 'remove_balance'
            detail = f'Provisional Balance {balance} is below -0.01'
            driver.close_record()
            removed.add(record.row)
            outcomes[record.key] = status
            if live:
                journal.put(record, reference, status, detail=detail)
            report(record, status, '', detail)
            continue
        transfer = driver.transfers()
        if transfer is None:
            status = 'remove_no_transfer'
            driver.close_record(financials=True)
            removed.add(record.row)
            outcomes[record.key] = status
            if live:
                journal.put(record, reference, status, detail='No Transfer after scanning the transaction table')
            report(record, status, '', 'No Transfer after scanning the transaction table')
            continue
        amount = royalty_amount(transfer)
        if live:
            driver.prepare_payment(amount, reference)
            # The intent is durable before the first of the three save/OK clicks.
            journal.put(record, reference, 'pending', amount, 'Save about to begin; inspect manually if interrupted')
            driver.commit_payment(amount, reference, balance)
            journal.put(record, reference, 'paid', amount, 'All three OK steps and balances verified')
            status = 'paid'
        else:
            driver.close_record(financials=True)
            status = 'would_pay'
        outcomes[record.key] = status
        report(record, status, amount, f'Transfer {transfer}; initial Provisional Balance {balance}')
    paid_licenses = journal.paid_licenses(reference)
    protected_rows = {record.row for record in records if record.license in paid_licenses}
    return removed - protected_rows


def run(source, sheet, first_row, reference, live, root, driver_factory, stop, log, progress=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with RunLock(root / 'run.lock'):
        reference = reference.strip()
        if not reference or any(c in reference for c in '\r\n\t'):
            raise ValueError('Enter a nonblank, single-line reference')
        workbook = Workbook(Path(source), sheet, first_row)
        if not workbook.records:
            raise ValueError('No valid license/publisher rows were found. Check the sheet and first data row.')
        total = len(workbook.records) + len(workbook.invalid)
        completed = 0
        notify = progress or (lambda *_: None)
        notify(0, total, 'Preparing workbook and run report…')
        folder = root / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        folder.mkdir()
        destination = folder / (Path(source).stem + '-filtered' + Path(source).suffix)
        # Check output access before any financial changes.
        workbook.save_filtered(destination, set(), use_excel=live)
        journal = Journal(root / 'journal.sqlite3')
        report_path = folder / 'report.csv'
        removed = set()
        failure = None
        try:
            with report_path.open('w', encoding='utf-8-sig', newline='') as out:
                writer = csv.writer(out)
                writer.writerow(['Original Excel row', 'License', 'Publisher', 'Status', 'Payment amount', 'Detail'])

                def report(record, status, amount, detail):
                    nonlocal completed
                    # Keep CSV fields as literal text if opened in Excel.
                    def safe(value):
                        text = str(value)
                        return "'" + text if text.startswith(('=', '+', '@')) else text
                    writer.writerow([record.row, safe(record.license), safe(record.publisher), status,
                                     str(amount), safe(detail)])
                    out.flush()
                    os.fsync(out.fileno())
                    if status.startswith('remove_'):
                        removed.add(record.row)
                    if status == 'duplicate' and 'first outcome: remove_' in detail:
                        removed.add(record.row)
                    log(f'Row {record.row}: {record.license} / {record.publisher}: {status}' + (f' ({amount})' if amount != '' else ''))
                    completed += 1
                    notify(completed, total, f'Processed Excel row {record.row}: {record.license} / {record.publisher} ({status})')

                for row, reason in workbook.invalid:
                    writer.writerow([row, '', '', 'review', '', reason])
                    completed += 1
                    notify(completed, total, f'Excel row {row} kept for review: {reason}')
                driver = driver_factory()
                try:
                    process_records(workbook.records, driver, reference, journal, live, report, stop)
                except Exception as exc:
                    failure = exc
                    writer.writerow(['', '', '', 'STOPPED', '', str(exc)])
                    out.flush()
                    os.fsync(out.fileno())
        finally:
            paid_licenses = journal.paid_licenses(reference)
            journal.close()
        protected_rows = {record.row for record in workbook.records if record.license in paid_licenses}
        retained = removed & protected_rows
        removed -= protected_rows
        if retained:
            log(f'Kept {len(retained)} otherwise excluded rows because another publisher for the same license received payment with this reference.')
            # Preserve the per-publisher decision and make the final workbook
            # disposition explicit, including on interrupted runs.
            with report_path.open(encoding='utf-8-sig', newline='') as source_report:
                report_rows = list(csv.reader(source_report))
            for row in report_rows[1:]:
                if row[0] and int(row[0]) in retained:
                    row[3] = 'keep_shared_license'
                    row[5] += '; row retained because another publisher for this license received payment'
            with report_path.open('w', encoding='utf-8-sig', newline='') as final_report:
                csv.writer(final_report).writerows(report_rows)
        # Preview always retains the original rows; only the report describes proposed removals.
        if not failure:
            notify(completed, total, 'Finalizing workbook and report—please wait…')
        if live and removed:
            try:
                workbook.save_filtered(destination, removed)
            except Exception as exc:
                raise RuntimeError(f'Entries already saved remain in License Manager. Could not create filtered workbook: {exc}. Original unchanged; use {report_path} to recover the removal decisions.') from exc
        log(f'Report: {report_path}')
        log(f'Workbook copy: {destination}')
        if failure:
            raise RuntimeError(f'{failure}\nPartial results: {folder}') from failure
        return folder
