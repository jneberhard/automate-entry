"""Read search digits without treating edit-frame strokes as extra ones."""
import re
import numpy as np
from PIL import Image, ImageOps


def search_images(image):
    gray = np.array(image.convert('L'))
    ink = gray < 210
    # Only full-length strokes at the outer frame qualify as borders. A short
    # digit '1' is preserved; no recognized digit is ever removed or changed.
    rows = ink.sum(axis=1) >= max(12,image.width*.7)
    cols = ink.sum(axis=0) >= max(8,image.height*.7)
    for y in range(image.height):
        if rows[y] and (y < 3 or y >= image.height-3):gray[y,:]=255
    for x in range(image.width):
        if cols[x] and (x < 3 or x >= image.width-3):gray[:,x]=255
    field=ImageOps.expand(Image.fromarray(gray),border=15,fill=255).convert('RGB')
    return [(field,scale) for scale in (2,3,4)]


def read_search_number(ocr,image):
    readings=[];values=[]
    for prepared,scale in search_images(image):
        text=' '.join(line.text for line in ocr.lines(prepared,scale=scale)).strip()
        readings.append(text)
        if re.fullmatch(r'\d[\d\s]*',text):values.append(''.join(text.split()))
    if len(values) < 2 or len(set(values)) > 1:
        confirmation=[]
        for prepared,scale in search_confirmation_images(image):
            text=' '.join(line.text for line in ocr.lines(prepared,scale=scale)).strip()
            readings.append(text)
            if re.fullmatch(r'\d[\d\s]*',text):confirmation.append(''.join(text.split()))
        if len(confirmation) >= 3 and len(set(confirmation)) == 1 and values.count(confirmation[0]) >= (2 if len(set(values)) > 1 else 1):
            return confirmation[0]
    if len(values) < 2 or len(set(values)) != 1:
        raise ValueError(f'Cannot read one exact search number: {readings!r}')
    return values[0]


def search_confirmation_images(image):
    from .identity_ocr import publisher_images
    return publisher_images(image)[:4]
