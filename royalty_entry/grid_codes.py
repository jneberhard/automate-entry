"""Locate exact PUB/PB codes anywhere in the visible search-result grid."""
import re
from .ocr import Line


def unhighlight_grid(image):
    """Turn white-on-blue selected rows into dark text on a light background.

    Preserve row coordinates so recovered codes still align with license rows.
    """
    import numpy as np
    from PIL import ImageOps
    pixels = np.asarray(image.convert('RGB')).astype('int16')
    blue = (pixels[:,:,2] > pixels[:,:,0]+40) & (pixels[:,:,2] > pixels[:,:,1]+10)
    selected = (blue.sum(axis=1) > image.width*.2).tolist()
    result = image.copy()
    start = None
    for y, active in enumerate(selected+[False]):
        if active and start is None:
            start = y
        elif not active and start is not None:
            band = image.crop((0,start,image.width,y)).convert('L')
            result.paste(ImageOps.autocontrast(ImageOps.invert(band)).convert('RGB'),(0,start))
            start = None
    return result


def publisher_codes(words):
    result = []
    for word in words:
        text = word.text.upper()
        match = re.fullmatch(r'(P(?:U|IJ|LI|LJ)B|PB)(\d+)', text)
        if match:
            # ClearType splits U into IJ/LI/LJ. Normalize only this bounded
            # prefix; digits and independently verified identities stay exact.
            code = ('PB' if match[1] == 'PB' else 'PUB') + match[2]
            result.append(Line(code, word.x, word.y, word.width, word.height))
        elif text in {'PUB', 'PIJB', 'PLIB', 'PLJB', 'PB'}:
            # Some fonts split prefix and digits into adjacent OCR words.
            neighbors = [other for other in words if re.fullmatch(r'\d+', other.text)
                         and abs((other.y+other.height/2)-(word.y+word.height/2)) < 4
                         and 0 <= other.x-(word.x+word.width) <= 12]
            if len(neighbors) == 1:
                other = neighbors[0]
                prefix = 'PB' if text == 'PB' else 'PUB'
                result.append(Line(prefix+other.text, word.x, word.y,
                                   other.x+other.width-word.x, word.height))
    return sorted(result, key=lambda line: (line.y, line.x))


def align_code_candidates(licenses, readings):
    """Combine exact OCR candidates by row, never by list index or fuzzy digits.

    A grid candidate still requires independent Properties verification before
    use. Different exact codes on the same row remain an error.
    """
    centers = [line.y+line.height/2 for line in licenses]
    if any(abs(y-z) < 10 for i, y in enumerate(centers) for z in centers[i+1:]):
        raise ValueError('License rows overlap')
    rows = []
    for line, center in zip(licenses, centers):
        candidates = [code for code in readings if abs(center-(code.y+code.height/2)) <= 5]
        if len({code.text for code in candidates}) != 1:
            raise ValueError('Missing or conflicting publisher codes on a license row')
        rows.append((line, candidates[0]))
    if any(not any(abs(center-(code.y+code.height/2)) <= 5 for center in centers) for code in readings):
        raise ValueError('Publisher code has no license row')
    return rows
