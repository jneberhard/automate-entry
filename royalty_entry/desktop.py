"""Runtime screen driver for the user's local Windows/Remote Desktop session."""
import ctypes
from ctypes import wintypes
import hashlib
import time
import re
from decimal import Decimal
from .ocr import WindowsOCR
from .rules import money, normalized


class ScreenError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def foreground():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    handle = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(2048)
    user32.GetWindowTextW(handle, title, len(title))
    rect = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        raise ScreenError('Cannot read the foreground window position')
    return handle, title.value, (rect.left, rect.top, rect.right, rect.bottom)


def capture_remote(profile):
    from PIL import ImageGrab
    handle, title, rect = foreground()
    if title != profile['window_title']:
        raise ScreenError('Remote Desktop must be the foreground window. No further input was sent.')
    size = (rect[2]-rect[0], rect[3]-rect[1])
    if list(size) != profile['window_size']:
        raise ScreenError(f'Remote Desktop is {size[0]}×{size[1]}; calibration expects {profile["window_size"]}. Restore its size or recalibrate.')
    return ImageGrab.grab(bbox=rect, all_screens=True), handle, rect


def aligned_rows(left, right, tolerance=5):
    """Pair independently read table columns only when every row aligns uniquely."""
    if len(left) != len(right):
        raise ScreenError('Table columns have different OCR row counts')
    result, used = [], set()
    for line in left:
        y = line.y + line.height/2
        candidates = [(i, other) for i, other in enumerate(right)
                      if abs(y-(other.y+other.height/2)) <= tolerance]
        if len(candidates) != 1 or candidates[0][0] in used:
            raise ScreenError('Cannot reliably align table rows')
        i, other = candidates[0]
        used.add(i)
        result.append((line, other))
    return result


class RemoteDriver:
    def __init__(self, profile, stop, log):
        import pyautogui
        self.pg = pyautogui
        self.pg.FAILSAFE = True
        self.pg.PAUSE = 0.15
        self.profile, self.stop, self.log = profile, stop, log
        self.ocr = WindowsOCR()
        self.record = None
        self.handle = None
        self.rect = None

    def check_stop(self):
        if self.stop.is_set():
            raise Cancelled('Stopped. If saving had begun, check the journal before restarting.')
        # Escape works even with RDP focused; mouse failsafe works on the primary screen.
        if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
            self.stop.set()
            raise Cancelled('Escape pressed; stopped')

    def wait(self, duration=None):
        if self.stop.wait(duration if duration is not None else self.profile['settle_seconds']):
            self.check_stop()
        self.check_stop()

    def snapshot(self):
        self.check_stop()
        image, handle, rect = capture_remote(self.profile)
        if self.handle is not None and handle != self.handle:
            raise ScreenError('The Remote Desktop window changed during the run')
        self.handle, self.rect = handle, rect
        return image

    def crop(self, image, key):
        return image.crop(self.profile['regions'][key])

    def text(self, image, key):
        return self.ocr.text(self.crop(image, key)).strip()

    def state(self, image):
        # More deeply nested dialogs take precedence over their visible parents.
        if normalized(self.text(image, 'chooser_title')) == 'transaction types':
            return 'chooser'
        if normalized(self.text(image, 'entry_title')) == 'financial transaction':
            return 'entry'
        title = normalized(self.text(image, 'financials_title'))
        if title.startswith('financial transactions for '):
            if self.record and not re.search(r'(?<!\d)' + re.escape(self.record.license) + r'(?!\d)', title):
                raise ScreenError('Financial Transactions belongs to another license')
            return 'financials'
        title = normalized(self.text(image, 'properties_title'))
        if title.endswith('properties') or (self.record and title.startswith(self.record.license + ' -')):
            if self.record and not title.startswith(self.record.license + ' '):
                raise ScreenError('Properties belongs to another license')
            if normalized(self.text(image, 'details_label')).replace(' ', '') == 'provisionalbalance:':
                return 'details'
            return 'general'
        if normalized(self.text(image, 'manager_title')) == 'license manager':
            return 'manager'
        raise ScreenError('Screen does not match a known License Manager step. No further input was sent.')

    def expect(self, stage):
        image = self.snapshot()
        actual = self.state(image)
        if actual != stage:
            raise ScreenError(f'Expected {stage}, found {actual}. Check the current dialog and calibration.')
        return image

    def ready(self, stage, timeout=12):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                return self.expect(stage)
            except ScreenError as exc:
                last = exc
                self.wait(0.4)
        raise ScreenError(f'Timed out waiting for {stage}: {last}')

    def click(self, point, stage, clicks=1):
        self.expect(stage)
        x, y = self.profile['points'][point] if isinstance(point, str) else point
        self.check_stop()
        self.pg.click(self.rect[0]+x, self.rect[1]+y, clicks=clicks, interval=0.15)
        self.wait()

    def keys(self, stage, *keys):
        self.expect(stage)
        self.pg.hotkey(*keys)
        self.wait()

    def paste(self, point, value, stage, region):
        import pyperclip
        self.click(point, stage)
        self.keys(stage, 'ctrl', 'a')
        pyperclip.copy(value)
        self.keys(stage, 'ctrl', 'v')
        # Remove the insertion caret before OCR (otherwise Q3| may be read as Q31).
        self.keys(stage, 'tab')
        image = self.expect(stage)
        actual = self.text(image, region)
        matches = money(actual) == money(value) if region == 'entry_amount' else normalized(actual) == normalized(value)
        if not matches:
            raise ScreenError(f'Pasted text could not be verified in {region}. Check RDP clipboard redirection.')

    def table(self, image, left_key, right_key):
        a, b = self.profile['regions'][left_key], self.profile['regions'][right_key]
        if a[1] != b[1] or a[3] != b[3]:
            raise ScreenError('Table column regions must have the same top and bottom')
        return aligned_rows(self.ocr.lines(self.crop(image, left_key)),
                            self.ocr.lines(self.crop(image, right_key)))

    def pages(self, stage, focus, left_key, right_key):
        self.click(focus, stage)
        self.keys(stage, 'ctrl', 'home')
        previous = None
        for _ in range(300):
            image = self.expect(stage)
            # Hash only the columns; the changing caret elsewhere does not matter.
            digest = hashlib.sha256(self.crop(image, left_key).tobytes() + self.crop(image, right_key).tobytes()).digest()
            if digest == previous:
                return
            previous = digest
            yield image, self.table(image, left_key, right_key)
            self.keys(stage, 'pagedown')
        raise ScreenError('Could not establish the end of the table after 300 pages')

    def open_record(self, record):
        self.record = record
        self.expect('manager')
        self.paste('search_input', record.license, 'manager', 'search_value')
        self.click('search_button', 'manager')
        deadline = time.monotonic()+12
        while True:
            image = self.expect('manager')
            count = self.text(image, 'search_count')
            match = re.search(r'\b(\d+)\s+Licenses?\b', count, re.I)
            if match and re.search(r'(?<!\d)' + re.escape(record.license) + r'(?!\d)', count):
                break
            if time.monotonic() > deadline:
                raise ScreenError('Could not verify fresh search results for this license')
            self.wait(0.5)
        if int(match[1]) == 0:
            return False
        for image, rows in self.pages('manager', 'result_focus', 'result_licenses', 'result_publishers'):
            matches = [(a, b) for a, b in rows if a.text.strip() == record.license
                       and normalized(b.text) == normalized(record.publisher)]
            if len(matches) > 1:
                raise ScreenError('Multiple identical license/publisher results need manual review')
            if matches:
                line, _ = matches[0]
                box = self.profile['regions']['result_licenses']
                self.click((box[0]+50, round(box[1]+line.y+line.height/2)), 'manager', clicks=2)
                image = self.ready('general')
                publisher = re.sub(r'^PUB\d+\s*[-–]\s*', '', self.text(image, 'general_publisher'), flags=re.I)
                if self.text(image, 'general_license') != record.license or normalized(publisher) != normalized(record.publisher):
                    raise ScreenError('Opened license/publisher identity could not be verified')
                return True
        return False

    def balance(self, stage, region):
        first = money(self.text(self.expect(stage), region))
        self.wait(0.35)
        second = money(self.text(self.expect(stage), region))
        if first != second:
            raise ScreenError('Balance readings disagree')
        return first

    def details(self):
        self.click('details_tab', 'general')
        self.ready('details')
        return self.balance('details', 'details_balance')

    def transfers(self):
        self.click('financials_button', 'details')
        self.ready('financials')
        found = []
        seen = set()
        for image, rows in self.pages('financials', 'financials_focus', 'financials_types', 'financials_amounts'):
            if not rows:
                # OCR silence alone is never evidence that no Transfer exists.
                raise ScreenError('No readable financial rows; leave this license for review')
            for kind, amount in rows:
                value = money(amount.text)
                if normalized(kind.text) == 'transfer':
                    # A repeated visible row across overlapping pages is the same transfer.
                    key = (kind.text, str(value))
                    if key not in seen:
                        found.append(value)
                        seen.add(key)
        if len(found) > 1:
            raise ScreenError('More than one Transfer amount found')
        return found[0] if found else None

    def prepare_payment(self, amount, reference):
        self.click('financials_add', 'financials')
        self.ready('entry')
        self.click('type_button', 'entry')
        image = self.ready('chooser')
        matches = [l for l in self.ocr.lines(self.crop(image, 'chooser_names'))
                   if normalized(l.text) == 'payment of royalties']
        if len(matches) != 1:
            raise ScreenError('Could not identify exactly one PAYMENT OF ROYALTIES type')
        line = matches[0]
        box = self.profile['regions']['chooser_names']
        self.click((round(box[0]+line.x+line.width/2), round(box[1]+line.y+line.height/2)), 'chooser')
        self.click('chooser_ok', 'chooser')
        image = self.ready('entry')
        if normalized(self.text(image, 'entry_type')) != 'payment of royalties':
            raise ScreenError('Selected transaction Type could not be verified')
        self.paste('entry_amount', f'{amount:.2f}', 'entry', 'entry_amount')
        self.paste('entry_reference', reference, 'entry', 'entry_reference')

    def commit_payment(self, amount, reference, before):
        image = self.expect('entry')
        if (normalized(self.text(image, 'entry_type')) != 'payment of royalties'
                or money(self.text(image, 'entry_amount')) != amount
                or self.text(image, 'entry_reference') != reference):
            raise ScreenError('Payment verification failed; no save click was sent')
        self.click('entry_ok', 'entry')
        self.ready('financials')
        expected = before + amount
        if self.balance('financials', 'financials_balance') != expected:
            raise ScreenError('Balance after adding the payment does not match; check manually before retrying')
        self.click('financials_ok', 'financials')
        self.ready('details')
        if self.balance('details', 'details_balance') != expected:
            raise ScreenError('Details balance does not match the new payment')
        self.click('properties_ok', 'details')
        self.ready('manager')

    def close_record(self, financials=False):
        if financials:
            self.click('financials_ok', 'financials')
            self.ready('details')
        self.click('properties_ok', 'details')
        self.ready('manager')
