"""Identify the remote module before applying its Maximize command."""
from .rules import normalized


def module_caption(ocr, image):
    lines = ocr.lines(image)
    matches = [line for line in lines if 'mechanical royalty module' in normalized(line.text)]
    if len(matches) != 1:
        raise ValueError('Cannot identify the Mechanical Royalty Module title bar. Bring the module and License Manager into view and retry.')
    line = matches[0]
    return round(line.x+line.width/2), round(line.y+line.height/2)


def verify_maximized(ocr, active, desktop_size):
    module_caption(ocr, active.crop((0, 0, active.width, min(active.height, 100))))
    width, height = desktop_size
    # A maximized window fills the remote work area, excluding its taskbar.
    # Allow frame borders and a taskbar on any edge, but not a restored window.
    if abs(active.width-width) > 80 or not height-128 <= active.height <= height+32:
        raise ValueError('Mechanical Royalty Module did not fill the remote desktop. Maximize it using its top-right square, then retry.')
