import ctypes
import sys
sys.coinit_flags = 0  # Keep WinRT OCR and Excel COM on the MTA worker model.

# All screen coordinates must use physical pixels on both monitors.
if sys.platform == 'win32':
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from royalty_entry.self_test import main as self_test
        raise SystemExit(self_test(sys.argv))
    from royalty_entry.gui import main
    main()
