import ctypes
from types import SimpleNamespace
import pytest
from royalty_entry import keyboard


def test_remote_chord_has_scan_codes_extended_navigation_and_reverse_releases(monkeypatch):
    class Call:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    captured = []
    def send(count, events, size):
        assert size == ctypes.sizeof(keyboard.Input)
        captured.extend((e.payload.keyboard.vk, e.payload.keyboard.scan, e.payload.keyboard.flags) for e in events)
        return count
    api = SimpleNamespace(SendInput=Call(send), MapVirtualKeyW=Call(lambda vk, mode: vk+100))
    monkeypatch.setattr(keyboard.ctypes, 'WinDLL', lambda *args, **kwargs: api)
    keyboard.chord('shift', 'end')
    assert captured == [(0x10, 0x10+100, 0), (0x23, 0x23+100, 1),
                        (0x23, 0x23+100, 3), (0x10, 0x10+100, 2)]
    assert ctypes.sizeof(keyboard.Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_partial_send_releases_keys_and_stops(monkeypatch):
    class Call:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    calls = []
    def send(count, events, size):
        calls.append([event.payload.keyboard.flags for event in events])
        return 1
    api = SimpleNamespace(SendInput=Call(send), MapVirtualKeyW=Call(lambda vk, mode: vk))
    monkeypatch.setattr(keyboard.ctypes, 'WinDLL', lambda *args, **kwargs: api)
    with pytest.raises(RuntimeError, match='complete'):
        keyboard.chord('ctrl', 'v')
    assert calls[-1] == [2, 2]

@pytest.mark.parametrize('name',['escape','esc'])
def test_properties_cancel_sends_escape_down_and_up(monkeypatch,name):
    class Call:
        def __init__(self,fn):self.fn=fn
        def __call__(self,*args):return self.fn(*args)
    events=[]
    def send(count,sequence,size):
        events.extend((item.payload.keyboard.vk,item.payload.keyboard.flags) for item in sequence)
        return count
    api=SimpleNamespace(SendInput=Call(send),MapVirtualKeyW=Call(lambda vk,mode:vk))
    monkeypatch.setattr(keyboard.ctypes,'WinDLL',lambda *a,**k:api)
    keyboard.chord(name)
    assert events==[(0x1B,0),(0x1B,2)]
