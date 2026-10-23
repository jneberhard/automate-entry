from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry import identity_ocr
from royalty_entry.ocr import Line


def reader(monkeypatch, values):
    image = Image.new('RGB', (300, 21))
    stream = iter(values)
    monkeypatch.setattr(identity_ocr, 'amount_images', lambda _: [(image, 4)]*(len(values)-1))
    ocr = SimpleNamespace(text=lambda _: next(stream),
                          lines=lambda *args, **kwargs: [Line(next(stream), 0, 0, 30, 10)])
    return ocr, image


def test_border_outlier_and_spaced_digits_need_independent_exact_agreement(monkeypatch):
    ocr, image = reader(monkeypatch, ['11264806917', '1264806917', '12648069 17', '', 'I264806917'])
    assert identity_ocr.read_identity(ocr, image, 'license') == '1264806917'


@pytest.mark.parametrize('values', [
    ['', '', ''], ['I264806917', 'I264806917', ''],
    ['1264806917', '', '126480691'],
    ['1264806917', '1264806917', '1264806918', '1264806918'],
])
def test_unreadable_or_conflicting_licenses_stop(values, monkeypatch):
    ocr, image = reader(monkeypatch, values)
    with pytest.raises(ValueError):
        identity_ocr.read_identity(ocr, image, 'license')


def test_publisher_code_is_removed_but_name_and_punctuation_remain_exact(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB297 - Birnamwood Publications', 'PUB 297 – BIRNAMWOOD Publications', ''])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'birnamwood publications'
    ocr, image = reader(monkeypatch, ['PUB3 - Word Music, Inc.', 'PUB3 - Word Music, Inc.'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'word music, inc.'


def test_confirmed_different_publishers_are_not_fuzzily_merged(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB1 - Music A', 'PUB1 - Music A', 'PUB2 - Music B', 'PUB2 - Music B'])
    with pytest.raises(ValueError):
        identity_ocr.read_identity(ocr, image, 'publisher')


def test_split_u_in_publisher_code_does_not_change_publisher_name(monkeypatch):
    ocr, image = reader(monkeypatch, ['PIJB297 - Birnamwood Publications',
                                    'PLIB297 - Birnamwood Publications',
                                    'PUB297 - Birnamwood Publications'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'birnamwood publications'


def test_publisher_requires_unique_repeated_winner_without_changing_name(monkeypatch):
    ocr, image = reader(monkeypatch, ['5 - Word Music, Inc.'] +
                        ['PUB775 - Word Music, Inc.']*4 + ['PUB775 - Word Musiq Inc.']*2)
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'word music, inc.'


def test_three_exact_publisher_reads_beat_split_ocr_errors(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB694 - B-Day Publishing']*3 +
                        ['PUB694 - a-Day Publishing']*2 + ['PUB694 - Publishing', 'PUBC4 - Publishing'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'b-day publishing'
