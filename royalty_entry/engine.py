import csv
from datetime import datetime
from pathlib import Path
import os
from .desktop import Cancelled, PaymentNotSaved
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


def _process_record(record, driver, reference, journal, live):
    if not driver.open_record(record):
        return 'review', '', f'No exact license/publisher match ({record.publisher_number or record.publisher}); row retained'
    balance = driver.details()
    if balance < -CENT:
        status = 'remove_balance'
        detail = f'Provisional Balance {balance} is below -0.01'
        driver.close_record()
        if live:
            journal.put(record, reference, status, detail=detail)
        return status, '', detail
    transfer = driver.transfers()
    if transfer is None:
        status = 'remove_no_transfer'
        driver.close_record(financials=True)
        if live:
            journal.put(record, reference, status, detail='No Transfer after scanning the transaction table')
        return status, '', 'No Transfer after scanning the transaction table'
    amount = royalty_amount(transfer, balance)
    if live:
        driver.prepare_payment(amount, reference)
        # The intent is durable before the first of the three save/OK clicks.
        journal.put(record, reference, 'pending', amount, 'Save about to begin; inspect manually if interrupted')
        try:
            driver.commit_payment(amount, reference, balance)
        except PaymentNotSaved as exc:
            # This explicit exception is raised only before the first OK.
            # Unknown failures after a save attempt must remain pending.
            journal.put(record, reference, 'not_saved', amount, str(exc))
            raise
        journal.put(record, reference, 'paid', amount, 'All three OK steps and balances verified')
        status = 'paid'
    else:
        driver.close_record(financials=True)
        status = 'would_pay'
    return status, amount, f'Transfer {transfer}; initial Provisional Balance {balance}'


def process_records(records, driver, reference, journal, live, report, stop):
    """Isolate record failures, retaining uncertain saves for manual review."""
    import sqlite3
    removed, outcomes, details = set(), {}, {}
    for record in records:
        if stop.is_set():
            raise Cancelled('Stopped between rows')
        if record.key in outcomes:
            status = outcomes[record.key]
            if status.startswith('remove_'):
                removed.add(record.row)
            detail = f'Skipped repeated license/publisher; first outcome: {status}'
            if status in {'error', 'review'}:
                detail += '; ' + details[record.key]
            report(record, 'duplicate', '', detail)
            continue
        previous = journal.get(record, reference)
        if previous and previous[0] == 'legacy_review':
            status, amount, detail = 'review', '', previous[2]
        elif previous and previous[0] == 'pending':
            status, amount, detail = 'error', previous[1], ('Unfinished save in the journal. Inspect this license/publisher in License Manager before retrying; no automatic retry was attempted.')
        elif previous and previous[0] == 'paid':
            status, amount, detail = 'already_paid', previous[1], 'Previously completed by this program with this reference'
        elif previous and previous[0].startswith('remove_'):
            status, amount, detail = previous[0], '', previous[2]
        else:
            try:
                status, amount, detail = _process_record(record, driver, reference, journal, live)
            except (Cancelled, sqlite3.Error):
                raise
            except Exception as exc:
                if type(exc).__name__ == 'FailSafeException':
                    raise
                status, amount, detail = 'error', '', f'{type(exc).__name__}: {exc}'
                outcomes[record.key], details[record.key] = status, detail
                report(record, status, amount, detail)
                # Never send blind clicks or OK while recovering. A failed
                # recovery is a session failure, not permission to keep typing.
                recover = getattr(driver, 'recover_after_error', None)
                if recover is None:
                    raise
                try:
                    recover()
                except Cancelled:
                    raise
                except Exception as recovery:
                    raise RuntimeError(f'{detail}; cannot safely return to License Manager: {recovery}') from recovery
                continue
        outcomes[record.key], details[record.key] = status, detail
        if status.startswith('remove_'):
            removed.add(record.row)
        report(record, status, amount, detail)
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
        if not workbook.records and not workbook.invalid:
            raise ValueError('No valid license/publisher-code rows were found. Check column G (PUB/PB code), column I (license), sheet and first data row.')
        total = len(workbook.records) + len(workbook.invalid)
        completed = 0
        notify = progress or (lambda *_: None)
        notify(0, total, 'Preparing workbook and run report…')
        folder = root / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        folder.mkdir()
        destination = folder / (Path(source).stem + '-filtered' + Path(source).suffix)
        # Check output access before any financial changes.
        workbook.save_filtered(destination, set(), use_excel=live)
        if live:
            workbook.save_results_tab(set())  # Fail before payments if the source cannot be updated.
        journal = Journal(root / 'journal.sqlite3')
        report_path = folder / 'report.csv'
        removed = set()
        error_rows, errors = set(), []
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
                    if status in {'error', 'review'} or (status == 'duplicate' and
                            any(f'first outcome: {kind}' in detail for kind in ('error', 'review'))):
                        error_rows.add(record.row)
                        errors.append((record.row, record.license, record.publisher_number, record.publisher, detail))
                    if status.startswith('remove_'):
                        removed.add(record.row)
                    if status == 'duplicate' and 'first outcome: remove_' in detail:
                        removed.add(record.row)
                    log(f'Row {record.row}: {record.license} / {record.publisher}: {status}' + (f' ({amount})' if amount != '' else ''))
                    completed += 1
                    notify(completed, total, f'Processed Excel row {record.row}: {record.license} / {record.publisher} ({status})')

                for row, reason in workbook.invalid:
                    writer.writerow([row, '', '', 'review', '', reason])
                    error_rows.add(row)
                    errors.append((row, '', '', '', reason))
                    completed += 1
                    notify(completed, total, f'Excel row {row} kept for review: {reason}')
                try:
                    if workbook.records:
                        driver = driver_factory()
                        process_records(workbook.records, driver, reference, journal, live, report, stop)
                except Exception as exc:
                    failure = exc
                    writer.writerow(['', '', '', 'STOPPED', '', str(exc)])
                    out.flush()
                    os.fsync(out.fileno())
        finally:
            paid_licenses = journal.paid_licenses(reference)
            journal.close()
        errors_path = folder / 'errors.csv'
        with errors_path.open('w', encoding='utf-8-sig', newline='') as error_file:
            error_writer = csv.writer(error_file)
            error_writer.writerow(['Original Excel row', 'License', 'Publisher code', 'Publisher', 'Error'])
            for row in errors:
                error_writer.writerow([("'"+str(value) if str(value).startswith(('=', '+', '@')) else value) for value in row])
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
        if (live and removed) or error_rows:
            try:
                workbook.save_filtered(destination, removed if live else set(), **({'error_rows': error_rows} if error_rows else {}))
            except Exception as exc:
                raise RuntimeError(f'Entries already saved remain in License Manager. Could not create filtered workbook: {exc}. Original unchanged; use {report_path} to recover the removal decisions.') from exc
        log(f'Report: {report_path}')
        log(f'Recovery workbook copy: {destination}')
        if live:
            try:
                tab = workbook.save_results_tab(removed, 'Royalty '+folder.name[:15], **({'error_rows': error_rows} if error_rows else {}))
            except Exception as exc:
                raise RuntimeError(f'Could not save the results tab: {exc}. Payments already saved remain in License Manager. Recovery workbook: {destination}. Report: {report_path}') from exc
            log(f'Results workbook: {workbook.path}')
            log(f'Results tab: {tab}')
        log(f'Errors needing review: {len(errors)} row(s). Error report: {errors_path}')
        for row, license_number, code, publisher, detail in errors:
            log(f'ERROR — Excel row {row}: {license_number} / {code}: {detail}')
        if failure:
            raise RuntimeError(f'{failure}\nPartial results: {folder}') from failure
        return folder
