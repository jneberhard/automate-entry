from decimal import Decimal
from types import SimpleNamespace
import pytest
from royalty_entry import desktop


def driver(monkeypatch):
    d = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    events = []
    d.handle = 12
    d.click = lambda *a: events.append('click')
    d.expect = lambda *a: None
    d.check_stop = lambda: None
    d.wait = lambda *a: None
    d.hotkey = lambda *a: events.append(a)
    d.pg = SimpleNamespace(write=lambda value, **kw: events.append(('typed', value)))
    monkeypatch.setattr(desktop, 'foreground', lambda: (12, '', None))
    return d, events


def test_amount_uses_keys_and_displayed_verification_not_text_clipboard(monkeypatch):
    import pyperclip
    d, events = driver(monkeypatch)
    monkeypatch.setattr(pyperclip, 'copy', lambda *_: pytest.fail('Amount must not use clipboard'))
    d.balance = lambda *a: Decimal('-.26')
    d.paste('entry_amount', '-0.26', 'entry', 'entry_amount')
    assert ('typed', '-0.26') in events
    assert events.index(('tab',)) > events.index(('typed', '-0.26'))


def test_wrong_displayed_amount_stops_without_retry_or_save(monkeypatch):
    d, events = driver(monkeypatch)
    d.balance = lambda *a: Decimal('0.26')
    with pytest.raises(desktop.ScreenError, match='No save click'):
        d.paste('entry_amount', '-0.26', 'entry', 'entry_amount')
    assert events.count('click') == 1


@pytest.mark.parametrize('readings,success', [
    (['HFA Payments 2026 Q3']*2, True),
    (['HFA Payments 2026 Q3', 'HFA Payments 2026 Q31'], False),
    (['Royalty Entry awaiting field text']*2, False),
])
def test_missing_copy_back_needs_two_exact_displayed_reference_reads(monkeypatch, readings, success):
    import pyperclip
    d, events = driver(monkeypatch)
    monkeypatch.setattr(pyperclip, 'copy', lambda *_: None)
    clock = iter([0, 9])
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: next(clock))
    answers = iter(readings)
    d.text = lambda *a: next(answers)
    if success:
        d.paste('entry_reference', 'HFA Payments 2026 Q3', 'entry', 'entry_reference')
    else:
        with pytest.raises(desktop.ScreenError, match='No save click'):
            d.paste('entry_reference', 'HFA Payments 2026 Q3', 'entry', 'entry_reference')
