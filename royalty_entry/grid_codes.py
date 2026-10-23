"""Locate exact PUB/PB codes anywhere in the visible search-result grid."""
import re
from .ocr import Line


def publisher_codes(words):
    result = []
    for word in words:
        text = word.text.upper()
        if re.fullmatch(r'(?:PUB|PB)\d+', text):
            result.append(Line(text, word.x, word.y, word.width, word.height))
        elif text in {'PUB', 'PB'}:
            # Some fonts split prefix and digits into adjacent OCR words.
            neighbors = [other for other in words if re.fullmatch(r'\d+', other.text)
                         and abs((other.y+other.height/2)-(word.y+word.height/2)) < 4
                         and 0 <= other.x-(word.x+word.width) <= 12]
            if len(neighbors) == 1:
                other = neighbors[0]
                result.append(Line(text+other.text, word.x, word.y,
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
