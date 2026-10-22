"""Non-interactive bundle test. Never captures the desktop or sends input."""
import json
from pathlib import Path


def main(args):
    target = Path(args[args.index('--self-test')+1])
    checks = {}
    try:
        import tkinter
        checks['tkinter'] = tkinter.Tcl().eval('info patchlevel')
        import openpyxl
        import pyautogui
        import pyperclip
        import pythoncom
        import win32com.client
        import winreg
        checks['excel_module'] = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, r'Excel.Application\CLSID')
        from .ocr import WindowsOCR
        from PIL import Image, ImageDraw, ImageFont
        from .paths import asset_root
        from .profile import load_profile
        image = Image.new('RGB', (620, 110), 'white')
        draw = ImageDraw.Draw(image)
        import os
        font = ImageFont.truetype(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/'arial.ttf'), 30)
        draw.text((12, 10), 'PAYMENT OF ROYALTIES', font=font, fill='black')
        draw.text((12, 55), '-0.91', font=font, fill='black')
        text = WindowsOCR().text(image)
        if 'PAYMENT OF ROYALTIES' not in text or '-0.91' not in text:
            raise RuntimeError(f'Unexpected OCR result: {text}')
        checks['local_ocr'] = text
        checks['icon'] = (asset_root()/'assets'/'royalty-entry.ico').is_file()
        if not checks['icon']:
            raise RuntimeError('Application icon is missing from the bundle')
        checks['default_profile'] = load_profile(asset_root()/'no-profile.json')['window_size']
        from .tracking import ToolbarTracker
        toolbar = Image.open(asset_root()/'assets'/'license-toolbar.png').convert('RGB')
        scene = Image.new('RGB', (1008, 711), '#eeeeee')
        scene.paste(toolbar.resize((225, 19)), (220, 95))
        found = ToolbarTracker().locate(scene)
        if abs(found.scale-.5) > .01:
            raise RuntimeError('Scaled-toolbar tracking test failed')
        checks['toolbar_scale'] = found.scale
        checks['ok'] = True
    except Exception as exc:
        import traceback
        checks['ok'] = False
        checks['error'] = str(exc)
        checks['traceback'] = traceback.format_exc()
    target.write_text(json.dumps(checks, indent=2), encoding='utf-8')
    return 0 if checks['ok'] else 1
