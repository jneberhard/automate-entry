from types import SimpleNamespace
import pytest
from PIL import Image
from royalty_entry.window_layout import find_smart_sizing, prepare_remote_window
from royalty_entry.tracking import ViewTransform


def test_smart_sizing_is_discovered_by_name_not_hardcoded_id():
    items = [{'text': 'Maximize', 'id': 1, 'state': 0}, {'text': '&Smart sizing', 'id': 987, 'state': 8}]
    assert find_smart_sizing(items)['id'] == 987
    assert find_smart_sizing(items)['state'] & 8


def test_missing_disabled_or_ambiguous_smart_sizing_is_not_guessed():
    with pytest.raises(ValueError):
        find_smart_sizing([])
    with pytest.raises(ValueError, match='disabled'):
        find_smart_sizing([{'text': 'Smart sizing', 'id': 1, 'state': 3}])
    with pytest.raises(ValueError):
        find_smart_sizing([{'text': 'Smart sizing', 'id': 1, 'state': 0}]*2)


def test_wrong_foreground_window_is_never_changed(monkeypatch):
    from royalty_entry import desktop
    monkeypatch.setattr(desktop, 'foreground', lambda: (1, 'Excel', (0, 0, 1008, 711)))
    with pytest.raises(desktop.ScreenError, match='intended Remote Desktop'):
        prepare_remote_window({'window_title': 'Remote Desktop'}, lambda _: None, lambda _: None)


def test_clicks_use_detected_scale_and_window_origin():
    from royalty_entry.desktop import RemoteDriver
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = {'points': {'search_button': [899, 241]}}
    driver.expect = lambda stage: None
    driver.check_stop = lambda: None
    driver.wait = lambda: None
    driver.transform = ViewTransform(.5, 10, 30)
    driver.raw_size = (1008, 711)
    clicks = []
    driver.pg = SimpleNamespace(click=lambda x, y, **kwargs: clicks.append((x, y)))
    driver.rect = (-1024, 0, -16, 711)
    driver.click('search_button', 'manager')
    assert clicks == [(-564, 150)]


def test_offscreen_control_never_receives_a_click():
    from royalty_entry.desktop import RemoteDriver, ScreenError
    driver = RemoteDriver.__new__(RemoteDriver)
    driver.profile = {'points': {'save': [2000, 1000]}}
    driver.expect = lambda stage: None
    driver.transform = ViewTransform(1, 0, 0)
    driver.raw_size = (1008, 711)
    driver.pg = SimpleNamespace(click=lambda *args, **kwargs: pytest.fail('Offscreen click'))
    with pytest.raises(ScreenError, match='outside the visible'):
        driver.click('save', 'entry')


def test_preparation_occurs_once_but_tracking_occurs_on_every_capture(monkeypatch):
    from royalty_entry import desktop, window_layout
    driver = desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    actions = []
    driver.profile = {'window_size': [1907, 1032]}
    driver.check_stop = lambda: None
    driver.wait = lambda _: None
    driver.log = lambda _: None
    driver.window_prepared, driver.handle, driver.transform = False, None, None
    def locate(image):
        actions.append('track')
        return ViewTransform(.5, 0, 30)
    driver.tracker = SimpleNamespace(locate=locate)
    driver.native_snapshot = lambda: Image.new('RGB', (1920, 1080))
    driver.read_tracker = SimpleNamespace(locate=lambda image: ViewTransform(1, 0, 0), reference=(447, 153))
    monkeypatch.setattr(window_layout, 'prepare_remote_window', lambda *args: actions.append('prepare'))
    monkeypatch.setattr(desktop, 'capture_remote', lambda profile: (Image.new('RGB', (1008, 711)), 1, (0, 0, 1008, 711)))
    assert driver.snapshot().size == (1907, 1032)
    assert driver.snapshot().size == (1907, 1032)
    assert actions == ['prepare', 'track', 'track']


def test_menu_state_is_refreshed_and_existing_smart_sizing_is_not_toggled_off(monkeypatch):
    from royalty_entry import desktop, window_layout
    monkeypatch.setattr(desktop, 'foreground', lambda: (1, 'Remote Desktop', (0, 0, 1008, 711)))
    state = {'enabled': False, 'checked': False, 'toggles': 0}
    class Call:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    def initialize(*args):
        state['checked'] = state['enabled']
        return 1
    def text(menu, position, buffer, length, flag):
        buffer.value = 'Smart sizing'
        return len(buffer.value)
    def toggle(handle, message, command, parameter):
        assert message == 0x112 and command == 987
        state['enabled'] = not state['enabled']
        state['toggles'] += 1
        return 1
    api = SimpleNamespace(GetSystemMenu=Call(lambda *args: 2), GetMenuItemCount=Call(lambda *args: 1),
                          GetMenuItemID=Call(lambda *args: 987), GetMenuStringW=Call(text),
                          GetMenuState=Call(lambda *args: 8 if state['checked'] else 0),
                          SendMessageTimeoutW=Call(initialize), PostMessageW=Call(toggle))
    monkeypatch.setattr(window_layout.ctypes, 'WinDLL', lambda *args, **kwargs: api)
    profile = {'window_title': 'Remote Desktop'}
    assert prepare_remote_window(profile, lambda _: None, lambda _: None)
    assert not prepare_remote_window(profile, lambda _: None, lambda _: None)
    assert state['enabled'] and state['toggles'] == 1
