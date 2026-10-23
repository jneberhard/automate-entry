"""Find an exact chooser label with repeated text and row agreement."""
from PIL import ImageOps
from .ocr import Line
from .rules import normalized


def exact_choice(ocr, image, label):
    target = normalized(label)
    gray = ImageOps.expand(image.convert('L'), border=12, fill='white').convert('RGB')
    passes = [(image, 3, 0), (gray, 4, 12), (gray, 6, 12)]
    hits, readings = [], []
    for prepared, scale, padding in passes:
        lines = ocr.lines(prepared, scale=scale)
        readings.append([line.text for line in lines])
        # The list's small row icon sometimes becomes a leading bullet. Strip
        # only those explicit icon glyphs, never letters or label punctuation.
        matches = [line for line in lines
                   if normalized(line.text.lstrip().lstrip('•·● ').lstrip()) == target]
        if len(matches) > 1:
            raise ValueError(f'Multiple exact {label} rows in chooser')
        if matches:
            line = matches[0]
            hits.append(Line(line.text, line.x-padding, line.y-padding, line.width, line.height))
    if len(hits) < 2:
        raise ValueError(f'Could not confirm exactly one {label} type: {readings!r}')
    centers = [line.y+line.height/2 for line in hits]
    if max(centers)-min(centers) > 5:
        raise ValueError(f'{label} chooser row readings disagree')
    return hits[0]
