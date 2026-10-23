from decimal import Decimal
from threading import Event
import pytest
from royalty_entry.engine import process_records
from royalty_entry.journal import Journal
from royalty_entry.rules import Record


class Driver:
    def __init__(self, balance='0', transfer='-.25', found=True, fail_save=False):
        self.value = Decimal(balance)
        self.transfer = None if transfer is None else Decimal(transfer)
        self.found, self.fail_save = found, fail_save
        self.opened, self.prepared, self.saved, self.closed = [], [], [], []

    def open_record(self, record):
        self.opened.append(record.key)
        return self.found

    def details(self):
        return self.value

    def transfers(self):
        return self.transfer

    def close_record(self, financials=False):
        self.closed.append(financials)

    def prepare_payment(self, amount, reference):
        self.prepared.append((amount, reference))

    def commit_payment(self, amount, reference, before):
        if self.fail_save:
            raise RuntimeError('Disconnected after save click')
        self.saved.append((amount, reference, before))


@pytest.fixture
def journal(tmp_path):
    journal = Journal(tmp_path/'journal.sqlite3')
    yield journal
    journal.close()


def run(journal, driver, records=None, live=True):
    rows = []
    removed = process_records(records or [Record(2, '123', 'Publisher')], driver, 'HFA Payment 2026 Q3',
                              journal, live, lambda *args: rows.append(args), Event())
    return removed, rows


@pytest.mark.parametrize('balance,should_pay', [('-.02', False), ('-.01', True), ('0', True), ('.01', True)])
def test_balance_threshold_is_strict(journal, balance, should_pay):
    driver = Driver(balance=balance)
    removed, rows = run(journal, driver)
    assert bool(driver.saved) is should_pay
    assert removed == (set() if should_pay else {2})


def test_missing_transfer_removes_all_duplicate_rows(journal):
    records = [Record(2, '123', 'Publisher'), Record(3, '123', 'PUBLISHER')]
    driver = Driver(transfer=None)
    removed, _ = run(journal, driver, records)
    assert removed == {2, 3}
    assert len(driver.opened) == 1
    assert not driver.saved


def test_same_license_different_publisher_is_processed(journal):
    records = [Record(2, '123', 'A'), Record(3, '123', 'A'), Record(4, '123', 'B')]
    driver = Driver()
    removed, _ = run(journal, driver, records)
    assert len(driver.saved) == 2
    assert len(driver.opened) == 2
    assert not removed
    assert driver.saved[0][0] == Decimal('-.26')


def test_preview_saves_no_payments_or_ledger_status(journal):
    driver = Driver()
    removed, rows = run(journal, driver, live=False)
    assert not driver.prepared and not driver.saved
    assert rows[0][1] == 'would_pay'
    assert journal.get(Record(2, '123', 'Publisher'), 'HFA Payment 2026 Q3') is None


def test_missing_match_keeps_row(journal):
    driver = Driver(found=False)
    removed, rows = run(journal, driver)
    assert not removed and not driver.saved
    assert rows[0][1] == 'review'


def test_completed_entry_not_repeated(journal):
    first = Driver()
    run(journal, first)
    second = Driver()
    _, rows = run(journal, second)
    assert not second.opened and not second.saved
    assert rows[0][1] == 'already_paid'


def test_interrupted_commit_blocks_automatic_retry(journal):
    with pytest.raises(RuntimeError, match='Disconnected'):
        run(journal, Driver(fail_save=True))
    assert journal.get(Record(2, '123', 'Publisher'), 'HFA Payment 2026 Q3')[0] == 'pending'
    driver = Driver()
    with pytest.raises(RuntimeError, match='unfinished save'):
        run(journal, driver)
    assert not driver.opened and not driver.saved


def test_reference_normalization_prevents_case_only_replays(journal):
    record = Record(2, '123', 'Publisher')
    journal.put(record, ' HFA Payment 2026 Q3 ', 'paid', '-.26')
    assert journal.get(record, 'hfa payment 2026 q3')[0] == 'paid'


@pytest.mark.parametrize('paid_first', [False, True])
def test_payment_keeps_other_publishers_and_duplicates_for_same_license(journal, paid_first):
    class MixedDriver(Driver):
        def open_record(self, record):
            self.current = record
            return super().open_record(record)
        def details(self):
            return Decimal('0') if self.current.publisher == 'Paid publisher' else Decimal('-1')
    records = [Record(2, '123', 'Excluded'), Record(3, '123', 'Excluded'),
               Record(4, '123', 'Paid publisher'), Record(5, '456', 'Excluded')]
    if paid_first:
        records = [records[2], *records[:2], records[3]]
    removed, _ = run(journal, MixedDriver(), records)
    assert removed == {5}


def test_prior_payment_protects_license_only_for_same_reference(journal):
    journal.put(Record(99, '123', 'Other publisher'), 'HFA Payment 2026 Q3', 'paid', '-.10')
    removed, _ = run(journal, Driver(balance='-1'), [Record(2, '123', 'Excluded')])
    assert removed == set()
    journal.put(Record(99, '456', 'Other publisher'), 'Different quarter', 'paid', '-.10')
    removed, _ = run(journal, Driver(balance='-1'), [Record(3, '456', 'Excluded')])
    assert removed == {3}


def test_publisher_number_upgrade_honors_existing_paid_journal(journal):
    journal.put(Record(2,'123','Publisher A'),'Q3','paid','-.10')
    assert journal.get(Record(2,'123','Publisher A','PUB832'),'Q3')[0]=='paid'
