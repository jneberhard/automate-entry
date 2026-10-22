"""Extract only the non-financial License Manager toolbar from a reference image."""
import sys
from pathlib import Path
from PIL import Image

source = Path(sys.argv[1])
target = Path(__file__).resolve().parent.parent/'assets'/'license-toolbar.png'
image = Image.open(source)
image.crop((10, 33, 460, 71)).save(target)
