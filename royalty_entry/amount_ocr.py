"""Prepare short monetary fields without discarding signs or guessing digits."""
import re
from PIL import Image, ImageOps


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


def amount_retry_images(image):
    """Alternate sampling for tiny zeroes that OCR otherwise reads as 'o'."""
    images = amount_images(image)
    if not images:
        return []
    field = images[0][0]
    # Keep the original pixels and sign; change rendering, never OCR characters.
    return [(field, scale) for scale in (2, 5, 7)] + [
        (field.resize((field.width*scale, field.height*scale),
                      Image.Resampling.NEAREST), 1) for scale in (3, 4)]


def read_amount(ocr, image):
    from .rules import money
    readings, valid = [], []
    def recognize(variants):
        for prepared, scale in variants:
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
    recognize(amount_images(image))
    original = list(valid)
    if len(set(original)) > 1:
        # Thresholding can erase a faint minus; enlargement can invent digits.
        # Resolve only with a fresh, unanimous batch of alternate renderings,
        # also supported by at least two original readings. Never majority-vote
        # conflicting results within that confirmation batch.
        valid.clear()
        recognize(amount_retry_images(image))
        if len(valid) >= 3 and len(set(valid)) == 1 and original.count(valid[0]) >= 2:
            return valid[0]
        raise ValueError(f'Monetary readings disagree: {readings!r}')
    if len(valid) < 2:
        recognize(amount_retry_images(image))
    if len(set(valid)) > 1:
        raise ValueError(f'Monetary readings disagree: {readings!r}')
    if len(valid) < 2:
        raise ValueError(f'Cannot read an exact monetary amount from the field: {readings!r}')
    return valid[0]


def read_table_amount(ocr, image):
    """Read one bounded table cell, including white text on a selected row."""
    import numpy as np
    from .rules import money
    gray = image.convert('L')
    if np.median(np.asarray(gray)) < 128:
        gray = ImageOps.autocontrast(ImageOps.invert(gray))
    valid, readings = [], []
    for prepared, scale in amount_images(gray):
        text = ' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
        readings.append(text)
        try:
            valid.append(money(text))
        except ValueError:
            continue
    if len(valid) < 2 or len(set(valid)) != 1:
        raise ValueError(f'Table amount readings do not agree: {readings!r}')
    return valid[0]
