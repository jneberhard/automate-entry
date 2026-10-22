"""Render the application's simple geometric icon at Windows icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw


root = Path(__file__).resolve().parent.parent
destination = root/'assets'
destination.mkdir(exist_ok=True)
image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=48, fill='#174A75')
draw.rounded_rectangle((59, 40, 182, 214), radius=13, fill='#F5FAFF')
for y in (77, 103, 129):
    draw.rounded_rectangle((80, y, 159, y+8), radius=4, fill='#89AEC8')
draw.ellipse((132, 140, 226, 234), fill='#36A77D', outline='#174A75', width=8)
draw.line([(154, 186), (171, 202), (204, 170)], fill='white', width=12, joint='curve')
image.save(destination/'royalty-entry.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
