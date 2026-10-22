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
    monkeypatch.setattr(amount_ocr, 'amount_images', lambda _: [(image, 4)]*6)
    stream = iter(answers)
    ocr = SimpleNamespace(lines=lambda *args, **kwargs: [Line(next(stream), 0, 0, 20, 10)])
    with pytest.raises(ValueError):
        amount_ocr.read_amount(ocr, image)


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
