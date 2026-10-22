# Reproducible, console-free Windows desktop distribution.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH)
datas = [(str(root/'assets'), 'assets')]
binaries = []
hiddenimports = ['win32timezone', 'pythoncom', 'pywintypes', 'win32com.client']
for package in ['winrt.runtime', 'winrt.system', 'winrt.windows.foundation',
                'winrt.windows.foundation.collections', 'winrt.windows.globalization',
                'winrt.windows.graphics.imaging', 'winrt.windows.media.ocr',
                'winrt.windows.storage.streams']:
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
hiddenimports += collect_submodules('win32com.client')
seed = root/'build-assets'/'initial-data'
if seed.exists():
    datas.append((str(seed), 'initial-data'))

a = Analysis([str(root/'app.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Royalty Entry',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root/'assets'/'royalty-entry.ico'),
          version=str(root/'version-info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Royalty Entry')
