from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry.choice_ocr import exact_choice
from royalty_entry.ocr import Line


def reader(passes):
    stream = iter(passes)
    return SimpleNamespace(lines=lambda *a, **kw: next(stream))


def test_clipped_initial_read_recovered_with_exact_agreement_and_coordinates():
    ocr = reader([[Line('AYMENT OF ROYALTIES', 0, 50, 120, 10)],
                  [Line('PAYMENT OF ROYALTIES', 14, 62, 120, 10)],
                  [Line('PAYMENT OF ROYALTIES', 14, 62, 120, 10)]])
    line = exact_choice(ocr, Image.new('RGB', (230, 85)), 'PAYMENT OF ROYALTIES')
    assert (line.x, line.y) == (2, 50)


def test_reported_icon_bullets_do_not_hide_exact_payment_label():
    ocr = reader([[Line('•PAYMENT OF ROYALTIES', 0, 50, 125, 10)],
                  [Line('•PAYMENT OF ROYALTIES', 12, 62, 125, 10)],
                  [Line('PAYMENT OF ROYALTIES', 12, 62, 120, 10)]])
    assert exact_choice(ocr, Image.new('RGB', (230, 85)), 'PAYMENT OF ROYALTIES').y == 50


@pytest.mark.parametrize('label', ['kPAYMENT OF ROYALTIES', 'PAYMENT OF ROYALTIES EXTRA',
                                  '•PAYMENT OF ROYALTIES EXTRA', '•PAYMENT OF ROYALTIE5'])
def test_icon_cleanup_never_accepts_altered_label(label):
    with pytest.raises(ValueError):
        exact_choice(reader([[Line(label, 0, 50, 125, 10)]]*3),
                     Image.new('RGB', (230, 85)), 'PAYMENT OF ROYALTIES')


@pytest.mark.parametrize('passes', [
    [[], [], []],
    [[Line('PAYMENT OF ROYALTIES', 0, 10, 120, 10)], [], []],
    [[Line('PAYMENT OF ROYALTIES', 0, 10, 120, 10)]*2],
    [[Line('PAYMENT OF ROYALTIES', 0, 10, 120, 10)],
     [Line('PAYMENT OF ROYALTIES', 12, 50, 120, 10)], []],
])
def test_missing_duplicate_or_disagreeing_rows_stop(passes):
    with pytest.raises(ValueError):
        exact_choice(reader(passes), Image.new('RGB', (230, 85)), 'PAYMENT OF ROYALTIES')


@pytest.mark.parametrize('key', ['chooser_names', 'entry_type'])
def test_type_crops_preserve_first_letter_left_of_saved_inset(key):
    from PIL import ImageDraw
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry.profile import DEFAULT
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = DEFAULT
    image = Image.new('RGB', tuple(DEFAULT['window_size']), 'white')
    left, top, _, _ = DEFAULT['regions'][key]
    ImageDraw.Draw(image).rectangle((left-2, top+3, left-1, top+10), fill='black')
    assert driver.crop(image, key).getextrema()[0][0] == 0
