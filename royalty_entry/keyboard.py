"""Send scan codes and extended-key flags that MSTSC forwards correctly."""
import ctypes
from ctypes import wintypes

KEYS = {'ctrl': 0x11, 'alt': 0x12, 'shift': 0x10, 'home': 0x24,
        'end': 0x23, 'pagedown': 0x22, 'tab': 0x09, 'add': 0x6B,
        'a': 0x41, 'c': 0x43, 'v': 0x56}
EXTENDED = {'home', 'end', 'pagedown'}


class KeyboardInput(ctypes.Structure):
    _fields_ = [('vk', wintypes.WORD), ('scan', wintypes.WORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('extra', ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG),
                ('data', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class Payload(ctypes.Union):
    _fields_ = [('keyboard', KeyboardInput), ('mouse', MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [('kind', wintypes.DWORD), ('payload', Payload)]


def chord(*keys):
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    api.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    events = []
    for release, order in ((False, keys), (True, reversed(keys))):
        for key in order:
            vk = KEYS[key]
            flags = (1 if key in EXTENDED else 0) | (2 if release else 0)
            item = Input(kind=1)
            item.payload.keyboard = KeyboardInput(vk, api.MapVirtualKeyW(vk, 0), flags, 0, 0)
            events.append(item)
    sequence = (Input * len(events))(*events)
    sent = api.SendInput(len(sequence), sequence, ctypes.sizeof(Input))
    if sent != len(sequence):
        # Release modifiers if Windows accepted only part of a chord.
        releases = events[len(keys):]
        cleanup = (Input * len(releases))(*releases)
        api.SendInput(len(cleanup), cleanup, ctypes.sizeof(Input))
        raise RuntimeError('Windows could not send the complete Remote Desktop keyboard shortcut')
