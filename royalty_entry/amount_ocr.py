"""Prepare short monetary fields without discarding signs or guessing digits."""
import re
from PIL import ImageOps


def amount_images(image):
    import numpy as np
    gray = image.convert('L')
    ink = np.asarray(gray) < 210
    # Legacy read-only edits have gray borders. Remove long border lines from
    # the bounding mask, while retaining faint minus signs and decimal points.
    ink[ink.sum(axis=1) >= max(12, gray.width*.7), :] = False
    ink[:, ink.sum(axis=0) >= max(8, gray.height*.7)] = False
    ys, xs = np.nonzero(ink)
    if not len(xs):
        return []
    box = (max(0, int(xs.min())-2), max(0, int(ys.min())-2),
           min(gray.width, int(xs.max())+3), min(gray.height, int(ys.max())+3))
    field = ImageOps.expand(gray.crop(box), border=12, fill='white')
    return [(field.convert('RGB'), 4), (field.convert('RGB'), 6),
            (field.point(lambda pixel: 0 if pixel < 140 else 255).convert('RGB'), 4),
            (field.point(lambda pixel: 0 if pixel < 140 else 255).convert('RGB'), 6),
            (field.point(lambda pixel: 0 if pixel < 180 else 255).convert('RGB'), 4),
            (field.point(lambda pixel: 0 if pixel < 180 else 255).convert('RGB'), 6)]


def read_amount(ocr, image):
    from .rules import money
    readings, valid = [], []
    for prepared, scale in amount_images(image):
        text = ' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
        readings.append(text)
        # These single-value fields display two decimals. A lost decimal point
        # must not turn -1.77 into a seemingly valid integer such as -177.
        if not re.search(r'\.\d{2}\)?$', text.replace(' ', '')):
            continue
        try:
            valid.append(money(text))
        except ValueError:
            continue
    if len(set(valid)) > 1:
        raise ValueError(f'Monetary readings disagree: {readings!r}')
    if len(valid) < 2:
        raise ValueError(f'Cannot read an exact monetary amount from the field: {readings!r}')
    return valid[0]
