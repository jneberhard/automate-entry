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


class PublisherMismatch(ScreenError):
    pass


class PaymentNotSaved(ScreenError):
    """Verification stopped before the first save click was attempted."""


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
    # GetWindowRect includes invisible Windows resize borders. Calibration and
    # screenshots use the visible frame, so prefer its physical screen bounds.
    try:
        dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmGetWindowAttribute.restype = ctypes.c_long
        visible = wintypes.RECT()
        result = dwm.DwmGetWindowAttribute(handle, 9, ctypes.byref(visible), ctypes.sizeof(visible))
        if result == 0 and visible.right > visible.left and visible.bottom > visible.top:
            rect = visible
    except (AttributeError, OSError):
        pass
    return handle, title.value, (rect.left, rect.top, rect.right, rect.bottom)


def capture_remote(profile):
    from PIL import ImageGrab
    handle, title, rect = foreground()
    if title != profile['window_title']:
        raise ScreenError('Remote Desktop must be the foreground window. No further input was sent.')
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
        self.window_prepared = False
        self.module_prepared = False
        from .tracking import ToolbarTracker
        self.tracker = ToolbarTracker()
        self.read_tracker = ToolbarTracker()
        self.transform = None
        self.raw_size = None

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
        if not self.window_prepared:
            from .window_layout import prepare_remote_window
            prepare_remote_window(self.profile, self.wait, self.log)
            self.window_prepared = True
        image, handle, rect = capture_remote(self.profile)
        if self.handle is not None and handle != self.handle:
            raise ScreenError('The Remote Desktop window changed during the run')
        self.handle, self.rect = handle, rect
        self.raw_size = image.size
        previous = self.transform
        self.transform = self.tracker.locate(image)
        if not getattr(self, 'module_prepared', True):
            self.prepare_module(image)
            self.module_prepared = True
            # Maximizing the parent can move its License Manager child. Locate
            # everything again before using any calibrated field or button.
            self.tracker.previous = self.read_tracker.previous = None
            return self.snapshot()
        if previous is None or abs(previous.scale-self.transform.scale) > .015:
            self.log(f'License Manager display scale: {self.transform.scale:.1%}; toolbar match: {self.transform.score:.0%}. '
                     'Screen reading and clicks now use this detected scale.')
        if self.transform.scale < .85:
            image = self.native_snapshot()
            reading = self.read_tracker.locate(image)
            reading = reading.native_pixels(self.read_tracker.reference)
            if reading.scale < .85:
                raise ScreenError('Remote Desktop returned a reduced snapshot. Enable clipboard image redirection and retry.')
            return reading.normalize(image, self.profile['window_size'])
        # Full-size visible captures need the same pixel-grid preservation as
        # native clipboard captures. A 99.78% toolbar match is fit noise, but
        # resampling it blurs small codes (e.g. PUB485 becomes PUB4S5).
        # Keep the measured transform for clicks; snap only the OCR reading.
        reading = self.transform.native_pixels(self.tracker.reference)
        return reading.normalize(image, self.profile['window_size'])

    def prepare_module(self, visible):
        from .module_layout import module_caption
        self.log('Maximizing Mechanical Royalty Module before the license sequence…')
        # At full size the visible capture already contains native-sized text.
        # Do not require clipboard images for this common case.
        native = visible if self.transform.scale >= .85 else self.native_snapshot()
        reading = self.read_tracker.locate(native).native_pixels(self.read_tracker.reference)
        if self.state(reading.normalize(native, self.profile['window_size'])) != 'manager':
            raise ScreenError('Close any license Properties or Financials dialogs and leave License Manager at the search screen before starting.')
        try:
            x, y = module_caption(self.ocr, native)
            logical = ((x-reading.x)/reading.scale, (y-reading.y)/reading.scale)
            x, y = self.transform.point(*logical)
            if not (0 <= x < self.raw_size[0] and 0 <= y < self.raw_size[1]):
                raise ValueError('Mechanical Royalty Module title bar is outside the visible remote view')
            self.check_stop()
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus before maximizing the module')
            self.pg.click(self.rect[0]+x, self.rect[1]+y)
            self.wait(.3)
            # Invoke the same Maximize command as the top-right square. Unlike
            # clicking that square blindly, this never restores an already
            # maximized module. Alt+Space targets the main frame, not an MDI child.
            self.hotkey('alt', 'space')
            self.wait(.3)
            self.hotkey('x')
            self.wait()
            after, handle, _ = capture_remote(self.profile)
            if handle != self.handle:
                raise ScreenError('Remote Desktop changed while maximizing the module')
            if self.transform.scale < .85:
                after = self.native_snapshot()
            module_caption(self.ocr, after)
        except ValueError as exc:
            raise ScreenError(str(exc)) from exc
        self.log('Mechanical Royalty Module Maximize command sent. Checking License Manager…')

    def native_snapshot(self):
        """RDP's documented Ctrl+Alt+numeric-plus captures native session pixels.

        Require a fresh clipboard sequence, never a previous screenshot. Image
        clipboard redirection supplies the pixels even when Smart sizing shrinks
        the displayed session. Click coordinates still use the visible toolbar.
        """
        from PIL import Image, ImageGrab
        import pyperclip
        # Remove any old bitmap before requesting the next one. RDP can update
        # clipboard metadata before its new image finishes arriving.
        self.check_stop()
        handle, title, _ = foreground()
        if handle != self.handle or title != self.profile['window_title']:
            raise ScreenError('Remote Desktop lost focus before screen reading')
        for attempt in range(3):
            self.check_stop()
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus before screen reading')
            pyperclip.copy('Royalty Entry screen capture')
            # Let the outgoing text/format notification finish before asking
            # the server for an image; otherwise it can overwrite that image.
            self.wait(.5)
            sequence = ctypes.windll.user32.GetClipboardSequenceNumber()
            self.hotkey('ctrl', 'alt', 'add')
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                self.wait(.1)
                if foreground()[0] != self.handle:
                    raise ScreenError('Remote Desktop lost focus during screen reading')
                if ctypes.windll.user32.GetClipboardSequenceNumber() == sequence:
                    continue
                try:
                    image = ImageGrab.grabclipboard()
                except OSError:
                    continue
                if isinstance(image, Image.Image):
                    return image.convert('RGB')
            if attempt < 2:
                self.log(f'Remote screenshot did not arrive; retrying ({attempt+2}/3)…')
                self.wait(.5)
        raise ScreenError('Remote screenshot did not arrive after 3 attempts. Clipboard images may be blocked or delayed. Use a full-size Remote Desktop view to read directly from the screen, or check RDP clipboard redirection.')

    def crop(self, image, key):
        box = list(self.profile['regions'][key])
        if key == 'result_licenses':
            # Keep the complete first digit. Some legacy grid themes draw the
            # number closer to the row icon than the calibration reference.
            box[0] = max(0, box[0]-16)
        if key in {'chooser_names', 'entry_type'}:
            # The legacy list can draw text left of the calibrated inset.
            # Include the complete first letter without including its icon.
            box[0] = max(0, box[0]-4)
        # Leave extra white-space at the right of numeric fields so a one-pixel
        # interpolation shift cannot cut off the last digit at smaller scales.
        if key == 'financials_amounts':
            # The numeric grid ends here: expanding this crop includes a
            # vertical separator that OCR can append as an extra digit.
            box[2] -= 2
        if key in {'entry_amount', 'details_balance', 'financials_balance'}:
            box[2] += 8
        return image.crop(box)

    def text(self, image, key):
        if key == 'search_value':
            from .search_ocr import read_search_number
            return read_search_number(self.ocr, self.crop(image, key))
        if key in {'entry_reference', 'entry_description'}:
            from .text_ocr import read_reference
            return read_reference(self.ocr, self.crop(image, key))
        if key in {'details_balance', 'financials_balance', 'entry_amount'}:
            from .amount_ocr import read_amount
            field = self.crop(image, key)
            try:
                return format(read_amount(self.ocr, field), 'f')
            except ValueError as exc:
                if getattr(self, 'log', None):
                    from .paths import data_root
                    diagnostic = data_root() / 'diagnostics' / f'{key}.png'
                    try:
                        diagnostic.parent.mkdir(parents=True, exist_ok=True)
                        field.save(diagnostic)
                        self.log(f'Unreadable amount diagnostic saved: {diagnostic}')
                    except OSError:
                        pass
                raise ValueError(f'{key}: {exc}') from exc
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
        x, y = self.transform.point(x, y)
        if not (0 <= x < self.raw_size[0] and 0 <= y < self.raw_size[1]):
            raise ScreenError('The required control is outside the visible remote view. Check Smart sizing and bring the dialog fully into view.')
        self.check_stop()
        self.pg.click(self.rect[0]+x, self.rect[1]+y, clicks=clicks, interval=0.15)
        self.wait()

    @staticmethod
    def hotkey(*keys):
        from .keyboard import chord
        chord(*keys)

    def keys(self, stage, *keys):
        self.expect(stage)
        self.hotkey(*keys)
        self.wait()

    def paste(self, point, value, stage, region):
        if region == 'search_value':
            if not re.fullmatch(r'\d+',value):
                raise ScreenError('Search requires an exact numeric license number')
            self.click(point,stage)
            self.expect(stage)
            self.hotkey('home')
            self.hotkey('shift','end')
            self.check_stop()
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus before entering the license')
            self.pg.write(value,interval=.08)
            self.wait()
            self.hotkey('tab')
            self.wait()
            first=self.text(self.expect(stage),region)
            self.wait(.35)
            second=self.text(self.expect(stage),region)
            if first != value or second != value:
                raise ScreenError(f'Entered license could not be verified: expected {value!r}, read {first!r} / {second!r}. Search was not submitted.')
            return
        if region == 'entry_amount':
            # This legacy numeric edit does not reliably implement Ctrl+C.
            # Enter ASCII amount keys directly and verify the displayed cents
            # twice, without relying on RDP text clipboard round trips.
            expected = money(value)
            self.click(point, stage)
            self.expect(stage)
            self.hotkey('home')
            self.hotkey('shift', 'end')
            self.check_stop()
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus before entering amount')
            self.pg.write(value, interval=.08)
            self.wait()
            self.hotkey('tab')
            self.wait()
            actual = self.balance(stage, region)
            if actual != expected:
                raise ScreenError(f'Entered amount could not be verified: expected {expected}, displayed {actual}. No save click was sent.')
            return
        import pyperclip
        self.click(point, stage)
        self.expect(stage)
        # Legacy License Manager combo/edit controls do not all implement Ctrl+A.
        self.hotkey('home')
        self.hotkey('shift', 'end')
        pyperclip.copy(value)
        # A screen check may use the image clipboard. Paste immediately after
        # copying text, without another capture replacing that text first.
        self.check_stop()
        if foreground()[0] != self.handle:
            raise ScreenError('Remote Desktop lost focus before pasting')
        self.hotkey('ctrl', 'v')
        self.wait()
        # Read back the editable field through RDP's text clipboard. Thin edit
        # borders and carets can look like extra digits to OCR, even at native
        # resolution. Exact clipboard text avoids accepting a fuzzy number.
        self.check_stop()
        if foreground()[0] != self.handle:
            raise ScreenError('Remote Desktop lost focus before verifying pasted text')
        self.hotkey('home')
        self.hotkey('shift', 'end')
        marker = 'Royalty Entry awaiting field text'
        pyperclip.copy(marker)
        self.hotkey('ctrl', 'c')
        deadline = time.monotonic() + 8
        actual = marker
        matches = False
        while time.monotonic() < deadline:
            self.wait(.1)
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus while verifying pasted text')
            actual = pyperclip.paste()
            # During RDP redirection the clipboard can briefly report empty or
            # an older text value before the selected remote text arrives.
            if actual != marker and actual.strip():
                try:
                    matches = money(actual) == money(value) if region == 'entry_amount' else actual.strip() == value.strip()
                except (ValueError, ArithmeticError):
                    matches = False
            if matches:
                break
        if not matches:
            # Some legacy edits accept a paste but cannot copy text back.
            # The clipboard marker is never evidence of the field's content.
            self.hotkey('tab')
            self.wait()
            first = self.text(self.expect(stage), region).strip()
            self.wait(.35)
            second = self.text(self.expect(stage), region).strip()
            if first != value.strip() or second != value.strip():
                raise ScreenError(f'Pasted text could not be verified in {region}: expected {value!r}, clipboard {actual!r}, displayed {first!r} / {second!r}. No save click was sent.')
            return
        # Remove the insertion caret before OCR (otherwise Q3| may be read as Q31).
        self.hotkey('tab')
        self.wait()
        self.expect(stage)

    def table(self, image, left_key, right_key):
        a, b = self.profile['regions'][left_key], self.profile['regions'][right_key]
        if a[1] != b[1] or a[3] != b[3]:
            raise ScreenError('Table column regions must have the same top and bottom')
        left = self.ocr.lines(self.crop(image, left_key))
        if right_key == 'result_publisher_numbers':
            from .grid_codes import publisher_codes
            grid = self.publisher_grid(image)
            counts = []
            readings = []
            for scale in (3, 4, 2):
                right = publisher_codes(self.ocr.words(grid, scale=scale))
                counts.append(len(right))
                readings.extend(right)
            from .grid_codes import align_code_candidates
            try:
                return align_code_candidates(left, readings)
            except ValueError:
                pass
            # Small white codes on the selected blue row can be omitted by
            # every whole-grid OCR pass. Remove selection colors and retry,
            # retaining the same coordinates and all exact-code conflicts.
            from .grid_codes import unhighlight_grid
            prepared = unhighlight_grid(grid)
            for scale in (2, 3, 4):
                right = publisher_codes(self.ocr.words(prepared, scale=scale))
                counts.append(len(right))
                readings.extend(right)
            try:
                return align_code_candidates(left, readings)
            except ValueError:
                pass
            from .grid_codes import recover_code_cells
            if getattr(self, 'log', None):
                from .paths import data_root
                diagnostic = data_root() / 'diagnostics' / 'publisher-grid.png'
                try:
                    diagnostic.parent.mkdir(parents=True, exist_ok=True)
                    grid.save(diagnostic)
                    self.log(f'Publisher-grid diagnostic saved: {diagnostic}')
                except OSError:
                    pass  # Diagnostics must never change the decision to stop.
            readings.extend(recover_code_cells(self.ocr, grid, left, readings))
            try:
                rows = align_code_candidates(left, readings, allow_missing=True)
                missing = sum(not code.text for _,code in rows)
                if missing and getattr(self, 'log', None):
                    self.log(f'{missing} grid publisher code(s) unreadable. These rows require independent Properties verification before matching.')
                return rows
            except ValueError as exc:
                raise ScreenError(f'Could not read an exact publisher code on every visible license row: {len(left)} licenses / {counts} whole-grid readings; {exc}. No publisher name was used for matching.') from exc
        right = self.ocr.lines(self.crop(image, right_key))
        try:
            return aligned_rows(left, right)
        except ScreenError:
            # A narrow amount column may lose a short value when the entire
            # column is recognized at once. Retry with contrast and whitespace
            # while retaining coordinates, so every row must still align.
            from PIL import ImageOps
            from .ocr import Line
            for scale in (4, 6):
                columns = []
                for key in (left_key, right_key):
                    gray = self.crop(image, key).convert('L')
                    prepared = ImageOps.expand(gray, border=12, fill='white').convert('RGB')
                    columns.append([Line(line.text, line.x-12, line.y-12, line.width, line.height)
                                    for line in self.ocr.lines(prepared, scale=scale)])
                try:
                    rows = aligned_rows(*columns)
                except ScreenError:
                    continue
                if rows:
                    return rows
            if right_key == 'financials_amounts' and left and len(right) < len(left):
                # Whole-column OCR can omit the short white amount in the
                # selected blue row. Read each cell inside its type's vertical
                # bounds instead; never associate an amount from another row.
                from .amount_ocr import read_table_amount
                column = self.crop(image, right_key)
                rows = []
                centers = [line.y+line.height/2 for line in left]
                if any(abs(y-z) < 12 for i, y in enumerate(centers) for z in centers[i+1:]):
                    raise ScreenError('Financial type rows overlap; cannot isolate amounts')
                for line in left:
                    if normalized(line.text) != 'transfer':
                        rows.append((line, Line('', 0, line.y, column.width, line.height)))
                        continue
                    center = line.y+line.height/2
                    cell = column.crop((0, max(0, round(center-7)), column.width,
                                        min(column.height, round(center+8))))
                    try:
                        value = read_table_amount(self.ocr, cell)
                    except ValueError as exc:
                        raise ScreenError(f'Cannot read amount beside {line.text!r} at table y={center:.1f}: {exc}') from exc
                    rows.append((line, Line(str(value), 0, line.y, column.width, line.height)))
                return rows
            raise ScreenError(f'Table columns could not be aligned: {left_key} / {right_key}; '
                              f'initial OCR counts {len(left)} / {len(right)}')

    def publisher_grid(self, image):
        regions = self.profile['regions']
        left, top, _, bottom = regions['result_licenses']
        right = max(regions['result_publishers'][2], regions['result_publisher_numbers'][2])
        return image.crop((max(0, left-16), top, right, bottom))

    def pages(self, stage, focus, left_key, right_key):
        self.click(focus, stage)
        self.keys(stage, 'ctrl', 'home')
        previous = None
        for _ in range(300):
            image = self.expect(stage)
            # Hash only the columns; the changing caret elsewhere does not matter.
            right_image = self.publisher_grid(image) if right_key == 'result_publisher_numbers' else self.crop(image, right_key)
            if left_key == right_key == 'financials_types':
                # Type-only pages can look identical. Include the complete
                # transaction rows in the scroll digest without OCR amounts.
                box = self.profile['regions']['financials_types']
                end = self.profile['regions']['financials_amounts'][2]
                right_image = image.crop((max(0,box[0]-210),box[1],end,box[3]))
            digest = hashlib.sha256(self.crop(image, left_key).tobytes() + right_image.tobytes()).digest()
            if digest == previous:
                return
            previous = digest
            yield image, self.table(image, left_key, right_key)
            if left_key == right_key == 'financials_types':
                # Cancel returns focus to Edit; restore the grid before scrolling.
                self.click(focus, stage)
            self.keys(stage, 'pagedown')
        raise ScreenError('Could not establish the end of the table after 300 pages')

    def open_record(self, record):
        if not record.publisher_number:
            return False
        self.record = record
        image = self.expect('manager')
        try:
            query = self.text(image, 'search_value').strip()
        except ValueError:
            query = ''  # A blank/unreadable old query must be replaced.
        current_count = self.text(image, 'search_count')
        reusable = (query == record.license
                    and re.search(r'\b\d+\s+Licenses?\b', current_count, re.I)
                    and re.search(r'(?<!\d)' + re.escape(record.license) + r'(?!\d)', current_count))
        if not reusable:
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
        if int(match[1]) == 1:
            # A single verified search result can be opened without decoding
            # its tiny grid code. Properties still independently confirms BOTH
            # complete identities before any financial step is allowed.
            lines = self.ocr.lines(self.crop(image, 'result_licenses'))
            if len(lines) == 1:
                box = self.profile['regions']['result_licenses']
                self.click((box[0]+50, round(box[1]+lines[0].y+lines[0].height/2)), 'manager', clicks=2)
                self.verify_open_identity(record, self.ready('general'))
                return True
        column = 'result_publisher_numbers'
        for image, rows in self.pages('manager', 'result_focus', 'result_licenses', column):
            def publisher_matches(line):
                return re.sub(r'\s+', '', line.text).upper() == record.publisher_number
            # The row icon can merge into the number's OCR on a selected row.
            # This only selects a candidate: Properties must independently
            # confirm the complete license number before any financial step.
            # Grid license glyphs are only candidate coordinates. Exact license
            # identity is independently required in Properties before use.
            matches = [(a, b) for a, b in rows if not b.text or publisher_matches(b)]
            for line, publisher_line in sorted(matches, key=lambda pair: pair[0].y):
                # Use the first visible exact match, including when OCR returns
                # rows out of order. Later pages and duplicate rows are skipped.
                box = self.profile['regions']['result_licenses']
                self.click((box[0]+50, round(box[1]+line.y+line.height/2)), 'manager', clicks=2)
                image = self.ready('general')
                try:
                    self.verify_open_identity(record, image)
                except PublisherMismatch:
                    if publisher_line.text:
                        raise  # A readable grid/Properties disagreement stops.
                    # This was only an unknown candidate. Cancel Properties
                    # and continue, preserving first-match order on the page.
                    self.keys('general', 'escape')
                    self.ready('manager')
                    continue
                return True
        return False

    def verify_open_identity(self, record, image):
        from .identity_ocr import read_identity
        if not record.publisher_number:
            raise ScreenError('Publisher code is required; names cannot be used for matching')
        confirmed = 0
        last = None
        # Dialog captions can paint before their edit fields. Alternate OCR
        # renderings of one incomplete frame cannot repair that; recapture.
        for attempt in range(4):
            if attempt:
                self.wait(.5)
                image = self.expect('general')
            try:
                license_number = read_identity(self.ocr, self.crop(image, 'general_license'), 'license')
                kind = 'publisher_number'
                publisher = read_identity(self.ocr, self.crop(image, 'general_publisher'), kind)
            except ValueError as exc:
                last = exc
                confirmed = 0
                continue
            if license_number != record.license:
                raise ScreenError(f'Opened license/publisher identity could not be verified. Expected '
                                  f'{record.license!r} / {record.publisher!r}; read {license_number!r} / {publisher!r}')
            expected = record.publisher_number
            if publisher != expected:
                raise PublisherMismatch(f'Opened publisher does not match: expected {expected!r}; read {publisher!r}')
            confirmed += 1
            if confirmed == 2:
                return
        raise ScreenError(f'Opened license/publisher identity did not stabilize across fresh screenshots: {last or "fewer than two consecutive confirmed frames"}')

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
        for image, rows in self.pages('financials', 'financials_focus', 'financials_types', 'financials_types'):
            if not rows:
                # OCR silence alone is never evidence that no Transfer exists.
                raise ScreenError('No readable financial rows; leave this license for review')
            for kind, amount in rows:
                if normalized(kind.text) == 'transfer':
                    value = self.read_transfer_entry(kind)
                    # A repeated visible row across overlapping pages is the same transfer.
                    key = (kind.text, str(value))
                    if key not in seen:
                        found.append(value)
                        seen.add(key)
        if len(found) > 1:
            raise ScreenError('More than one Transfer amount found')
        return found[0] if found else None

    def read_transfer_entry(self, line):
        """Inspect the existing transaction, then Cancel; never save an edit."""
        box = self.profile['regions']['financials_types']
        self.click((round(box[0]+line.x+line.width/2),round(box[1]+line.y+line.height/2)), 'financials')
        self.click('financials_edit','financials')
        image = self.ready('entry')
        try:
            readings = []
            for attempt in range(2):
                if attempt:
                    self.wait(.35)
                    image = self.expect('entry')
                kind = normalized(self.text(image,'entry_type'))
                description = normalized(self.text(image,'entry_description'))
                value = money(self.text(image,'entry_amount'))
                if kind != 'transfer' or description != 'transfer to publisher':
                    raise ScreenError(f'Expected TRANSFER / Transfer to publisher, read {kind!r} / {description!r}; no transaction was changed')
                readings.append(value)
            if readings[0] != readings[1]:
                raise ScreenError(f'Transfer Amount changed across screenshots: {readings!r}')
            return readings[0]
        finally:
            self.keys('entry','escape')
            self.ready('financials')

    def prepare_payment(self, amount, reference):
        self.click('financials_add', 'financials')
        self.ready('entry')
        self.click('type_button', 'entry')
        image = self.ready('chooser')
        from .choice_ocr import exact_choice
        try:
            line = exact_choice(self.ocr, self.crop(image, 'chooser_names'), 'PAYMENT OF ROYALTIES')
        except ValueError as exc:
            raise ScreenError(str(exc)) from exc
        box = self.profile['regions']['chooser_names']
        self.click((round(max(0, box[0]-4)+line.x+line.width/2), round(box[1]+line.y+line.height/2)), 'chooser')
        self.click('chooser_ok', 'chooser')
        image = self.ready('entry')
        if normalized(self.text(image, 'entry_type')) != 'payment of royalties':
            raise ScreenError('Selected transaction Type could not be verified')
        self.paste('entry_amount', f'{amount:.2f}', 'entry', 'entry_amount')
        self.paste('entry_reference', reference, 'entry', 'entry_reference')

    def verify_payment_fields(self, amount, reference):
        try:
            for attempt in range(2):
                if attempt:
                    self.wait(.35)
                image = self.expect('entry')
                actual = (normalized(self.text(image, 'entry_type')),
                          money(self.text(image, 'entry_amount')),
                          self.text(image, 'entry_reference'))
                expected = ('payment of royalties', amount, reference)
                errors = [f'{field}: expected {wanted!r}, read {read!r}'
                          for field, wanted, read in zip(('Type', 'Amount', 'Reference'), expected, actual)
                          if wanted != read]
                if errors:
                    raise ScreenError('; '.join(errors))
        except (ScreenError, ValueError) as exc:
            raise PaymentNotSaved(f'Payment verification failed: {exc}. No save click was sent.') from exc

    def commit_payment(self, amount, reference, before):
        self.verify_payment_fields(amount, reference)
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

    def recover_after_error(self):
        """Cancel recognized dialogs, never OK, and prove search is ready."""
        for _ in range(7):
            self.check_stop()
            image = self.snapshot()
            stage = self.state(image)
            if stage == 'manager':
                self.wait(.35)
                self.expect('manager')
                self.record = None
                return
            if stage not in {'chooser', 'entry', 'financials', 'general', 'details'}:
                raise ScreenError('Cannot identify the open dialog for safe cancellation')
            if foreground()[0] != self.handle:
                raise ScreenError('Remote Desktop lost focus during error recovery')
            self.hotkey('escape')
            self.wait(.35)
        raise ScreenError('Could not close the recognized dialogs and return to License Manager')
