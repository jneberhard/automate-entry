from decimal import Decimal
from types import SimpleNamespace
from PIL import Image, ImageDraw
import pytest
from royalty_entry import amount_ocr
from royalty_entry.ocr import Line


@pytest.mark.parametrize('answers,expected', [
    (['', '-1.77', '', '-1.77', '', ''], Decimal('-1.77')),
    (['0.00']*6, Decimal('0.00')),
    (['-.01']*6, Decimal('-.01')),
    (['1,234.56']*6, Decimal('1234.56')),
])
def test_agreed_exact_amounts(answers, expected, monkeypatch):
    image = Image.new('RGB', (100, 21))
    monkeypatch.setattr(amount_ocr, 'amount_images', lambda _: [(image, 4)]*6)
    stream = iter(answers)
    ocr = SimpleNamespace(lines=lambda *args, **kwargs: [Line(next(stream), 0, 0, 20, 10)])
    assert amount_ocr.read_amount(ocr, image) == expected


@pytest.mark.parametrize('answers', [
    ['']*6, ['-177']*6, ['0']*6, ['O.OO']*6,
    ['-1.77', '', '', '', '', ''],
    ['-1.77', '-1.77', '1.77', '', '', ''],
    ['-1.77', '-1.77', '-1.70', '', '', ''],
])
def test_blank_missing_decimal_or_disagreeing_digits_never_become_an_amount(answers, monkeypatch):
    image = Image.new('RGB', (100, 21))
    monkeypatch.setattr(amount_ocr, 'amount_retry_images', lambda _: [])
    monkeypatch.setattr(amount_ocr, 'amount_images', lambda _: [(image, 4)]*6)
    stream = iter(answers)
    ocr = SimpleNamespace(lines=lambda *args, **kwargs: [Line(next(stream), 0, 0, 20, 10)])
    with pytest.raises(ValueError):
        amount_ocr.read_amount(ocr, image)


@pytest.mark.parametrize('extra,expected', [
    (['-0.13']*5, Decimal('-0.13')),
    (['o.13']*5, None),
    (['0.13']*5, None),
    (['-0.13', '-0.18', '', '', ''], None),
])
def test_small_zero_retry_requires_exact_agreement(extra, expected, monkeypatch):
    image = Image.new('RGB', (100, 21))
    monkeypatch.setattr(amount_ocr, 'amount_images', lambda _: [(image, 4)]*6)
    monkeypatch.setattr(amount_ocr, 'amount_retry_images', lambda _: [(image, 2)]*5)
    responses = iter(['-o. 13', '-0.13', 'o. 13', 'o. 13', '', ''] + extra)
    ocr = SimpleNamespace(lines=lambda *a, **kw: [Line(next(responses), 0, 0, 20, 10)])
    if expected is None:
        with pytest.raises(ValueError):
            amount_ocr.read_amount(ocr, image)
    else:
        assert amount_ocr.read_amount(ocr, image) == expected


def test_blank_gray_edit_border_is_not_text():
    image = Image.new('RGB', (120, 21), (240, 240, 240))
    ImageDraw.Draw(image).rectangle((0, 0, 111, 20), outline=(160, 160, 160))
    assert amount_ocr.amount_images(image) == []


def test_faint_minus_is_preserved_in_numeric_crop():
    import numpy as np
    image = Image.new('RGB', (120, 21), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.line((80, 10, 84, 10), fill=(190, 190, 190))
    draw.rectangle((90, 7, 93, 14), fill='black')
    prepared, _ = amount_ocr.amount_images(image)[0]
    assert (np.asarray(prepared) == (190, 190, 190)).all(axis=2).any()


def test_selected_table_cell_is_inverted_and_requires_agreement(monkeypatch):
    import numpy as np
    image = Image.new('RGB', (60, 15), (0, 100, 180))
    def prepare(gray):
        assert np.median(np.asarray(gray)) > 128
        return [(gray, 4)]*3
    monkeypatch.setattr(amount_ocr, 'amount_images', prepare)
    responses = iter(['-.1', '', '-0.10'])
    ocr = SimpleNamespace(lines=lambda *a, **kw: [Line(next(responses), 0, 0, 20, 10)])
    assert amount_ocr.read_table_amount(ocr, image) == Decimal('-.10')


def test_blue_selected_background_does_not_erase_white_digits():
    import numpy as np
    image = Image.new('RGB', (60, 15), (0, 100, 180))
    ImageDraw.Draw(image).text((30, 1), '-.1', fill='white')
    seen = []
    def recognize(prepared, **kwargs):
        pixels = np.asarray(prepared.convert('L'))
        assert pixels.min() == 0 and pixels.max() == 255
        seen.append(prepared)
        return [Line('-.1', 0, 0, 20, 10)]
    assert amount_ocr.read_table_amount(SimpleNamespace(lines=recognize), image) == Decimal('-.1')
    assert len(seen) >= 2
