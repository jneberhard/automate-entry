"""Read identity edits exactly, preserving digits and publisher punctuation."""
from collections import Counter
import re
from .amount_ocr import amount_images
from .rules import normalized


def read_identity(ocr, image, kind):
    raw = [ocr.text(image).strip()]
    # The same border removal and ClearType enlargement used for amount fields
    # also prevents edit borders from looking like extra license-number digits.
    raw.extend(' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
               for prepared, scale in amount_images(image))
    values = []
    for text in raw:
        if kind == 'license':
            # Spaces between OCR digit groups are formatting, never substitute
            # letters or infer missing digits from the expected license.
            if re.fullmatch(r'\d[\d\s]*', text):
                values.append(''.join(text.split()))
        elif kind == 'publisher':
            # ClearType can split the U in the non-identity PUB code into IJ
            # or LI. Only normalize this bounded code; never alter the name.
            text = re.sub(r'^P(?:U|IJ|LI)B\s*\d+\s*[-–]\s*', '', text, flags=re.I)
            if normalized(text):
                values.append(normalized(text))
        else:
            raise ValueError('Unknown identity field')
    counts = Counter(values)
    confirmed = [value for value, count in counts.items() if count >= 2]
    if kind == 'publisher':
        minimum = min(3, len(raw)//2+1)
        confirmed = [value for value, count in counts.items()
                     if count >= minimum and all(count > other_count for other, other_count in counts.items()
                                                 if other != value)]
    if len(confirmed) != 1:
        raise ValueError(f'Cannot read one agreed {kind} identity: {raw!r}')
    return confirmed[0]
