"""Identify the remote module before applying its Maximize command."""
from .rules import normalized


def module_caption(ocr, image):
    lines = ocr.lines(image)
    matches = [line for line in lines if 'mechanical royalty module' in normalized(line.text)]
    if len(matches) != 1:
        raise ValueError('Cannot identify the Mechanical Royalty Module title bar. Bring the module and License Manager into view and retry.')
    line = matches[0]
    return round(line.x+line.width/2), round(line.y+line.height/2)
