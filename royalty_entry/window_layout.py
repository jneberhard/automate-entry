"""Enable Remote Desktop's existing fit-to-window display option."""
import ctypes
from ctypes import wintypes


def find_smart_sizing(items):
    matches = [item for item in items if item['text'].replace('&', '').strip().casefold() == 'smart sizing']
    if len(matches) != 1:
        raise ValueError('Could not find Remote Desktop’s Smart sizing command. Enable Smart sizing in its title-bar menu and retry.')
    if matches[0]['state'] & 3:
        raise ValueError('Remote Desktop’s Smart sizing command is disabled')
    return matches[0]


def prepare_remote_window(profile, wait, log):
    from .desktop import foreground, ScreenError
    handle, title, _ = foreground()
    if title != profile['window_title']:
        raise ScreenError('Click inside the intended Remote Desktop window to start.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.GetMenuItemCount.argtypes = [wintypes.HMENU]
    user32.GetMenuItemID.argtypes = [wintypes.HMENU, ctypes.c_int]
    user32.GetMenuItemID.restype = wintypes.UINT
    user32.GetMenuStringW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int, wintypes.UINT]
    user32.GetMenuState.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user32.GetMenuState.restype = wintypes.UINT
    menu = user32.GetSystemMenu(handle, False)
    # MSTSC updates check marks when its menu is initialized. Querying the menu
    # without that notification can incorrectly show Smart sizing as unchecked.
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                         wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                         ctypes.POINTER(ctypes.c_size_t)]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    result = ctypes.c_size_t()
    for message, parameter in ((0x116, 0), (0x117, 0x10000)):
        if not user32.SendMessageTimeoutW(handle, message, menu, parameter, 2, 1000, ctypes.byref(result)):
            raise ScreenError('Remote Desktop is not responding while preparing its display menu')
    items = []
    for position in range(max(0, user32.GetMenuItemCount(menu))):
        text = ctypes.create_unicode_buffer(512)
        user32.GetMenuStringW(menu, position, text, len(text), 0x400)
        items.append({'text': text.value, 'id': user32.GetMenuItemID(menu, position),
                      'state': user32.GetMenuState(menu, position, 0x400)})
    try:
        command = find_smart_sizing(items)
    except ValueError as exc:
        raise ScreenError(str(exc)) from exc
    if command['state'] & 8:
        log('Smart sizing is enabled. Locating the scaled License Manager toolbar…')
        return False
    latest, title, _ = foreground()
    if latest != handle or title != profile['window_title']:
        raise ScreenError('Remote Desktop lost focus before enabling Smart sizing')
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    if not user32.PostMessageW(handle, 0x112, command['id'], 0):
        raise ScreenError('Could not enable Smart sizing. Enable it in Remote Desktop’s title-bar menu.')
    log('Enabled Remote Desktop Smart sizing. The window stays at its current size.')
    wait(max(2.5, profile.get('settle_seconds', 1.2)))
    return True
