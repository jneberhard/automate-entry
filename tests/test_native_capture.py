from types import SimpleNamespace
from PIL import Image, ImageGrab
import pytest
from royalty_entry import desktop


def test_small_view_reads_native_pixels_but_keeps_visible_click_transform(monkeypatch):
    from royalty_entry.tracking import ViewTransform
    driver = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    driver.profile = {'window_size': [1907, 1032]}
    driver.window_prepared, driver.handle, driver.transform = True, None, None
    driver.check_stop = lambda: None
    driver.log = lambda _: None
    driver.tracker = SimpleNamespace(locate=lambda _: ViewTransform(.5, 10, 30))
    driver.read_tracker = SimpleNamespace(locate=lambda _: ViewTransform(1, 0, 0), reference=(447, 153))
    driver.native_snapshot = lambda: Image.new('RGB', (1920, 1080), 'green')
    monkeypatch.setattr(desktop, 'capture_remote', lambda _: (Image.new('RGB', (1008, 711)), 1, (-1024, 0, -16, 711)))
    reading = driver.snapshot()
    assert reading.getpixel((500, 500)) == (0, 128, 0)
    assert driver.transform.point(900, 240) == (460, 150)
    assert driver.raw_size == (1008, 711)


def test_native_capture_ignores_stale_image_and_waits_for_fresh_clipboard(monkeypatch):
    import pyperclip
    monkeypatch.setattr(pyperclip, 'copy', lambda _: None)
    driver = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    driver.profile, driver.handle = {'window_title': 'Remote Desktop'}, 12
    events = []
    driver.check_stop = lambda: None
    driver.wait = lambda _: None
    driver.hotkey = lambda *keys: events.append(keys)
    values = iter([3, 3, 4])
    monkeypatch.setattr(desktop.ctypes, 'windll', SimpleNamespace(user32=SimpleNamespace(GetClipboardSequenceNumber=lambda: next(values))))
    monkeypatch.setattr(desktop, 'foreground', lambda: (12, 'Remote Desktop', (0, 0, 1008, 711)))
    def grab():
        events.append('fresh image')
        return Image.new('RGB', (1920, 1080))
    monkeypatch.setattr(ImageGrab, 'grabclipboard', grab)
    assert driver.native_snapshot().size == (1920, 1080)
    assert events == [('ctrl', 'alt', 'add'), 'fresh image']


def test_no_screen_capture_overwrites_text_between_copy_and_paste(monkeypatch):
    import pyperclip
    driver = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    events = []
    driver.handle = 12
    driver.click = lambda *args: None
    driver.keys = lambda stage, *keys: events.append(keys)
    driver.expect = lambda _: events.append('screen')
    driver.check_stop = lambda: None
    driver.wait = lambda *args: None
    driver.text = lambda *args: '1234567890'
    driver.hotkey = lambda *keys: events.append(keys)
    monkeypatch.setattr(pyperclip, 'copy', lambda value: events.append('copy text'))
    arriving = iter(['', 'Royalty Entry awaiting field text', '1234567890'])
    monkeypatch.setattr(pyperclip, 'paste', lambda: next(arriving))
    monkeypatch.setattr(desktop, 'foreground', lambda: (12, 'Remote Desktop', (0, 0, 1008, 711)))
    driver.paste('search_input', '1234567890', 'manager', 'search_value')
    index = events.index('copy text')
    assert events[index+1] == ('ctrl', 'v')
    assert events.count(('shift', 'end')) == 2
    assert ('ctrl', 'a') not in events
