from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry.module_layout import module_caption
from royalty_entry.ocr import Line


class OCR:
    def lines(self, image):
        return [Line('Mechanical Royalty Module (BYU Music Group) v7.5.2.2', 5, 4, 440, 14)]


def test_caption_identifies_main_module_not_license_child():
    assert module_caption(OCR(), Image.new('RGB', (1920, 1080))) == (225, 11)
    with pytest.raises(ValueError, match='identify'):
        module_caption(SimpleNamespace(lines=lambda _: [Line('License Manager', 3, 3, 100, 15)]), Image.new('RGB', (1920, 1080)))


@pytest.mark.parametrize('stage', ['manager', 'details'])
@pytest.mark.parametrize('scale', [.5, 1])
def test_maximize_precedes_sequence_and_full_size_never_uses_image_clipboard(monkeypatch, stage, scale):
    from royalty_entry import desktop
    from royalty_entry.tracking import ViewTransform
    driver = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    driver.handle = 42
    driver.profile = {'window_size': [1907, 1032]}
    driver.state = lambda _: stage
    driver.ocr = OCR()
    driver.transform = ViewTransform(scale, 0, 30)
    driver.read_tracker = SimpleNamespace(reference=(447, 153), locate=lambda _: ViewTransform(1, 0, 0))
    driver.raw_size, driver.rect = (1008, 711), (-1024, 0, -16, 711)
    events = []
    driver.pg = SimpleNamespace(click=lambda x, y: events.append(('click', x, y)))
    driver.hotkey = lambda *keys: events.append(keys)
    driver.log, driver.check_stop, driver.wait = lambda _: None, lambda: None, lambda *args: None
    def native():
        if scale == 1:
            pytest.fail('Full-size startup must not require a clipboard screenshot')
        return Image.new('RGB', (1920, 1080))
    driver.native_snapshot = native
    visible = Image.new('RGB', (1920, 1080))
    monkeypatch.setattr(desktop, 'capture_remote', lambda _: (visible, 42, driver.rect))
    monkeypatch.setattr(desktop, 'foreground', lambda: (42, 'Remote Desktop', driver.rect))
    if stage != 'manager':
        with pytest.raises(desktop.ScreenError, match='Close any license'):
            driver.prepare_module(visible)
        assert events == []
        return
    driver.prepare_module(visible)
    assert events[0] == ('click', -1024+round(225*scale), round(30+11*scale))
    assert ('alt', 'space') in events and ('x',) in events
