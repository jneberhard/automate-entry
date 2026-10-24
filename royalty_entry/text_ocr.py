"""Read small reference edits without guessing letters or punctuation."""
from collections import Counter
from .identity_ocr import publisher_images


def read_reference(ocr, image):
    # White padding prevents the edit border from hiding a short reference.
    raw = [' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
           for prepared, scale in publisher_images(image)]
    values = [text for text in raw if text]
    counts = Counter(values)
    winners = [text for text, count in counts.items()
               if count >= 3 and count*4 >= len(values)*3
               and all(count > other for key, other in counts.items() if key != text)]
    if len(winners) != 1:
        raise ValueError(f'Cannot read one agreed payment reference: {raw!r}')
    return winners[0]
