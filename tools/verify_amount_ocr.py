"""Offline regression against the supplied number-only balance screenshot."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from decimal import Decimal
from PIL import Image
from royalty_entry.amount_ocr import read_amount
from royalty_entry.ocr import WindowsOCR

image = Image.open(Path(__file__).resolve().parent.parent/'tests/fixtures/provisional-balance.png')
ocr = WindowsOCR()
for scale in (1, .925):
    sample = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.BILINEAR)
    sample = sample.resize(image.size, Image.Resampling.BICUBIC)
    value = read_amount(ocr, sample)
    assert value == Decimal('-1.77'), (scale, value)
    print(f'{scale:.1%} reference balance: {value}', flush=True)
