import json
import pytest
from royalty_entry.desktop import aligned_rows, ScreenError
from royalty_entry.ocr import Line
from royalty_entry.profile import DEFAULT, load_profile


@pytest.mark.parametrize('dwm_result,expected', [(0, (0, 0, 1907, 1032)), (-1, (-7, 0, 1914, 1039))])
def test_visible_window_bounds_exclude_invisible_resize_border(monkeypatch, dwm_result, expected):
    from royalty_entry import desktop

    class Call:
        def __init__(self, function):
            self.function = function

        def __call__(self, *args):
            return self.function(*args)

    def window_text(handle, text, count):
        text.value = 'Remote Desktop'
        return len(text.value)

    def window_rect(handle, pointer):
        pointer._obj.left, pointer._obj.top = -7, 0
        pointer._obj.right, pointer._obj.bottom = 1914, 1039
        return 1

    def visible_rect(handle, attribute, pointer, size):
        assert attribute == 9
        pointer._obj.left, pointer._obj.top = 0, 0
        pointer._obj.right, pointer._obj.bottom = 1907, 1032
        return dwm_result

    from types import SimpleNamespace
    user32 = SimpleNamespace(GetForegroundWindow=Call(lambda: 1), GetWindowTextW=Call(window_text), GetWindowRect=Call(window_rect))
    dwm = SimpleNamespace(DwmGetWindowAttribute=Call(visible_rect))
    monkeypatch.setattr(desktop.ctypes, 'WinDLL', lambda name, **kwargs: user32 if name == 'user32' else dwm)
    assert desktop.foreground() == (1, 'Remote Desktop', expected)


def test_independent_column_rows_match_by_height():
    types = [Line('PAYMENT OF ROYALTIES', 1, 0, 200, 12), Line('TRANSFER', 1, 17, 80, 12)]
    amounts = [Line('-0.9', 1, 18, 24, 11), Line('-1.01', 1, 1, 30, 11)]
    rows = aligned_rows(types, amounts)
    assert rows[1][1].text == '-0.9'


def test_missing_or_ambiguous_amount_never_matches():
    left = [Line('TRANSFER', 1, 17, 80, 12)]
    with pytest.raises(ScreenError):
        aligned_rows(left, [])
    with pytest.raises(ScreenError):
        aligned_rows(left, [Line('-.9', 1, 40, 22, 12)])


def test_table_retry_recovers_short_amount_without_shifting_rows():
    from types import SimpleNamespace
    from PIL import Image
    from royalty_entry.desktop import RemoteDriver
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = {'regions': {'types': [0, 0, 100, 60], 'amounts': [100, 0, 140, 60]}}
    driver.crop = lambda image, key: Image.new('RGB', (100 if key == 'types' else 40, 60), 'white')
    responses = iter([
        [Line('TRANSFER', 0, 20, 60, 10)], [],
        [Line('TRANSFER', 12, 32, 60, 10)], [Line('-.25', 12, 32, 24, 10)],
    ])
    driver.ocr = SimpleNamespace(lines=lambda *args, **kwargs: next(responses))
    rows = driver.table(None, 'types', 'amounts')
    assert rows[0][0].y == rows[0][1].y == 20
    assert rows[0][1].text == '-.25'


def test_missing_historical_amount_does_not_block_exact_transfer_cell(monkeypatch):
    from types import SimpleNamespace
    from decimal import Decimal
    from PIL import Image
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry import amount_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = {'regions': {'types': [0, 0, 100, 60], 'financials_amounts': [100, 0, 140, 60]}}
    driver.crop = lambda image, key: Image.new('RGB', (40, 60), 'white')
    types = [Line('PAYMENT OF ROYALTIES', 0, 0, 30, 10), Line('TRANSFER', 0, 20, 30, 10)]
    responses = iter([types, [], types, [], types, []])
    driver.ocr = SimpleNamespace(lines=lambda *a, **kw: next(responses))
    calls = []
    def read(ocr, image):
        calls.append(image.size)
        return Decimal('-.25')
    monkeypatch.setattr(amount_ocr, 'read_table_amount', read)
    rows = driver.table(None, 'types', 'financials_amounts')
    assert len(calls) == 1
    assert rows[0][1].text == ''
    assert rows[1][1].text == '-0.25'


def test_default_profile_and_invalid_coordinates(tmp_path):
    path = tmp_path/'profile.json'
    assert load_profile(path)['window_size'] == [1907, 1032]
    data = json.loads(json.dumps(DEFAULT))
    data['regions']['manager_title'] = [-1, 0, 12, 12]
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(path)


def test_financial_amount_crop_excludes_grid_separator():
    from PIL import Image, ImageDraw
    from royalty_entry.desktop import RemoteDriver
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = DEFAULT
    image = Image.new('RGB', tuple(DEFAULT['window_size']), 'white')
    x0, y0, x1, y1 = DEFAULT['regions']['financials_amounts']
    ImageDraw.Draw(image).line((x1-1, y0, x1-1, y1), fill='black')
    assert driver.crop(image, 'financials_amounts').getextrema() == ((255, 255),)*3


def test_transfer_rechecks_cell_instead_of_trusting_column_ocr(monkeypatch):
    from PIL import Image
    from decimal import Decimal
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry import amount_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.ocr = object()
    driver.click = lambda *a: None
    driver.ready = lambda *a: None
    driver.crop = lambda *a: Image.new('RGB', (58, 80), 'white')
    rows = [(Line('TRANSFER', 0, 20, 60, 10), Line('.o.1F', 0, 20, 30, 10))]
    driver.pages = lambda *a: [(None, rows)]
    monkeypatch.setattr(amount_ocr, 'read_table_amount', lambda *a: Decimal('-.12'))
    assert driver.transfers() == Decimal('-.12')


def test_first_visible_exact_license_publisher_result_is_opened(monkeypatch):
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry.rules import Record
    from royalty_entry import identity_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = DEFAULT
    driver.ocr = object()
    driver.expect = lambda stage: object()
    driver.paste = lambda *args: None
    driver.text = lambda *args: '3 Licenses (Number: 123)'
    driver.ready = lambda stage: object()
    driver.wait = lambda seconds: None
    driver.crop = lambda image, region: region
    monkeypatch.setattr(identity_ocr, 'read_identity',
                        lambda ocr, image, kind: '123' if kind == 'license' else 'publisher a')
    rows = [(Line('123', 0, y, 50, 10), Line(pub, 0, y, 80, 10))
            for y, pub in [(40, 'Publisher A'), (0, 'Publisher B'), (20, 'Publisher A')]]
    driver.pages = lambda *args: iter([(object(), rows)])
    clicks = []
    driver.click = lambda point, stage, **kwargs: clicks.append((point, kwargs))
    assert driver.open_record(Record(2, '123', 'Publisher A'))
    box = DEFAULT['regions']['result_licenses']
    assert clicks[-1] == ((box[0]+50, box[1]+25), {'clicks': 2})


def test_identity_retries_fresh_frames_after_incomplete_dialog(monkeypatch):
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry.rules import Record
    from royalty_entry import identity_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.ocr = object()
    frames = iter(['second', 'third'])
    driver.expect = lambda stage: next(frames)
    driver.wait = lambda seconds: None
    driver.crop = lambda image, region: (image, region)
    seen = []
    def read(ocr, field, kind):
        frame, region = field
        seen.append((frame, kind))
        if frame == 'first': raise ValueError('Publisher text in unfinished license field')
        return '123' if kind == 'license' else 'publisher a'
    monkeypatch.setattr(identity_ocr, 'read_identity', read)
    driver.verify_open_identity(Record(2, '123', 'Publisher A'), 'first')
    assert seen == [('first', 'license'), ('second', 'license'), ('second', 'publisher'),
                    ('third', 'license'), ('third', 'publisher')]


def test_readable_wrong_identity_stops_without_retry_or_input(monkeypatch):
    from royalty_entry.desktop import RemoteDriver, ScreenError
    from royalty_entry.rules import Record
    from royalty_entry import identity_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.ocr = object()
    driver.crop = lambda image, region: region
    driver.wait = lambda seconds: pytest.fail('Wrong identity must stop immediately')
    monkeypatch.setattr(identity_ocr, 'read_identity', lambda ocr, image, kind: '999' if kind == 'license' else 'publisher a')
    with pytest.raises(ScreenError, match='identity could not be verified'):
        driver.verify_open_identity(Record(2, '123', 'Publisher A'), object())


def test_unreadable_identity_stops_after_bounded_fresh_captures(monkeypatch):
    from royalty_entry.desktop import RemoteDriver, ScreenError
    from royalty_entry.rules import Record
    from royalty_entry import identity_ocr
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.ocr = object()
    captures = []
    driver.expect = lambda stage: captures.append(stage)
    driver.wait = lambda seconds: None
    driver.crop = lambda *args: None
    def unreadable(*args): raise ValueError('No digits')
    monkeypatch.setattr(identity_ocr, 'read_identity', unreadable)
    with pytest.raises(ScreenError, match='did not stabilize'):
        driver.verify_open_identity(Record(2, '123', 'Publisher A'), object())
    assert captures == ['general']*3


def test_number_matching_does_not_depend_on_publisher_name(monkeypatch):
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry.rules import Record
    driver=RemoteDriver.__new__(RemoteDriver)
    driver.profile=DEFAULT
    driver.expect=lambda stage:None
    driver.paste=lambda *args:None
    driver.text=lambda *args:'2 Licenses (Number: 123)'
    driver.ready=lambda stage:None
    driver.click=lambda *a,**kw:None
    driver.pages=lambda *a:[(None,[(Line('123',0,0,40,10),Line('PUB831',0,0,50,10)),
                                 (Line('123',0,20,40,10),Line('PUB832',0,20,50,10))])]
    verified=[]
    driver.verify_open_identity=lambda record,image:verified.append(record.publisher_number)
    assert driver.open_record(Record(2,'123','Completely different display spelling','PUB832'))
    assert verified==['PUB832']
