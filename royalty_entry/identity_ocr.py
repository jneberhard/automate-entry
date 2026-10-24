"""Read identity edits exactly, preserving digits and publisher punctuation."""
from collections import Counter
import re
from .amount_ocr import amount_images
from .rules import normalized


def publisher_images(image):
    from PIL import ImageOps
    variants = []
    for trim in (0, 1):
        cell = image.crop((0, trim, image.width, image.height-trim))
        for mode in ('RGB', 'L'):
            field = ImageOps.expand(cell.convert(mode), border=15,
                                    fill='white' if mode == 'RGB' else 255).convert('RGB')
            variants.extend((field, scale) for scale in (2, 3))
    return variants


def publisher_code_images(image):
    # Reduce OCR's word context around the leading code. The separator must
    # still be recognized, so clipping a longer code cannot yield a match.
    variants = []
    for width, trim in ((70, 0), (80, 1)):
        cell = image.crop((0, trim, min(width, image.width), image.height-trim))
        variants.extend(publisher_images(cell)[:4])
    return variants


def clipped_publisher_candidate(line, expected, width):
    visible = normalized(line.text).removesuffix('...').removesuffix('…').rstrip()
    return (len(visible) >= 24 and line.x+line.width >= width-16
            and normalized(expected).startswith(visible))


def read_identity(ocr, image, kind):
    if kind == 'publisher_number':
        # Clear codes need only four unanimous low-magnification renderings.
        # Any blank, disagreement, or malformed code uses the full reader below.
        quick = []
        variants = publisher_images(image)[:4]
        for prepared, scale in variants:
            text = ' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
            match = re.match(r'^\s*(PUB|PB)\s*(\d+)\s*[-–]', text, re.I)
            quick.append(match[1].upper()+match[2] if match and (match[1].upper() != 'PB' or match[2].startswith('1')) else None)
        if len(quick) == 4 and quick[0] is not None and len(set(quick)) == 1:
            return quick[0]
        isolated = []
        for index, (prepared, scale) in enumerate(publisher_code_images(image)):
            text = ' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
            match = re.match(r'^\s*(PUB|PB)\s*(\d+)\s*[-–]', text, re.I)
            isolated.append(match[1].upper()+match[2] if match and (match[1].upper() != 'PB' or match[2].startswith('1')) else None)
            group = isolated[-4:]
            if (index+1) % 4 == 0 and len(group) == 4 and group[0] is not None and len(set(group)) == 1:
                # Each crop must agree across both color modes and scales.
                # A border-free crop recovers glyphs obscured by edit borders.
                return group[0]
        # Blanks/malformed glyphs are not conflicting codes. Require at least
        # four exact reads, supported by both crop boundaries, and reject any
        # different valid code. The caller also checks two fresh screenshots.
        valid = [value for value in isolated if value is not None]
        groups = [isolated[i:i+4] for i in range(0, len(isolated), 4)]
        if (len(valid) >= 4 and len(set(valid)) == 1
                and sum(sum(value is not None for value in group) >= 2 for group in groups) >= 2):
            return valid[0]
    raw = [ocr.text(image).strip()]
    # The same border removal and ClearType enlargement used for amount fields
    # also prevents edit borders from looking like extra license-number digits.
    raw.extend(' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
               for prepared, scale in amount_images(image))
    if kind in {'publisher', 'publisher_number'}:
        raw.extend(' '.join(line.text for line in ocr.lines(prepared, scale=scale)).strip()
                   for prepared, scale in publisher_images(image))
    values = []
    for text in raw:
        if kind == 'license':
            # Spaces between OCR digit groups are formatting, never substitute
            # letters or infer missing digits from the expected license.
            if re.fullmatch(r'\d[\d\s]*', text):
                values.append(''.join(text.split()))
        elif kind == 'publisher_number':
            # Read only the leading code, never digits from the publisher name.
            match = re.match(r'^\s*(P(?:U|IJ|LI)B|PB)\s*(\d+)\s*[-–]', text, re.I)
            if match and (match[1].upper() != 'PB' or match[2].startswith('1')):
                prefix = 'PB' if match[1].upper() == 'PB' else 'PUB'
                values.append(prefix + match[2])
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
    if kind == 'publisher_number' and len(confirmed) > 1:
        # A high-contrast rendering can repeatedly read 8 as 6. Resolve only
        # an overwhelming exact-code consensus (at least 80% of valid reads),
        # never by substituting digits or by preferring the expected workbook
        # value. The caller still verifies this code on two fresh screenshots.
        confirmed = [value for value, count in counts.items()
                     if count >= 3 and count*5 >= len(values)*4
                     and all(count > other for key, other in counts.items() if key != value)]
    if kind == 'publisher':
        minimum = min(3, len(raw)//2+1)
        confirmed = [value for value, count in counts.items()
                     if count >= minimum and all(count > other_count for other, other_count in counts.items()
                                                 if other != value)]
    if len(confirmed) != 1:
        detail = f'; isolated code readings: {isolated!r}' if kind == 'publisher_number' else ''
        raise ValueError(f'Cannot read one agreed {kind} identity: {raw!r}{detail}')
    return confirmed[0]
