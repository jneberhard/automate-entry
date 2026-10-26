import copy
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from .profile import load_profile
from .workbook import sheet_names
from .paths import asset_root, data_root, initialize_data
from .start_gate import RemoteClickGate


ROOT = data_root()
PROFILE = ROOT / 'calibration' / 'profile.json'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Royalty Entry — Remote Desktop')
        icon = asset_root() / 'assets' / 'royalty-entry.ico'
        if icon.exists():
            self.iconbitmap(str(icon))
        width = min(820, max(620, self.winfo_screenwidth()-80))
        height = min(720, max(580, self.winfo_screenheight()-120))
        self.geometry(f'{width}x{height}+20+20')
        self.minsize(min(760, width), min(660, height))
        self.option_add('*Font', '{Segoe UI} 10')
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.waiting_for_remote = False
        self.remote_wait_job = None
        self.progress_total = 0
        self.source = tk.StringVar()
        self.sheet = tk.StringVar()
        self.reference = tk.StringVar()
        self.first = tk.StringVar(value='2')
        self.live = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Choose a saved workbook to begin.')
        panel = ttk.Frame(self, padding=22)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Royalty Entry', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='Excel → License Manager through your local Remote Desktop window').pack(anchor='w', pady=(0, 18))
        form = ttk.Frame(panel)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text='Excel file').grid(row=0, column=0, sticky='w', padx=(0, 14), pady=7)
        ttk.Entry(form, textvariable=self.source, state='readonly').grid(row=0, column=1, sticky='ew')
        self.browse = ttk.Button(form, text='Browse…', command=self.choose_file)
        self.browse.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(form, text='Worksheet').grid(row=1, column=0, sticky='w', pady=7)
        self.sheet_box = ttk.Combobox(form, textvariable=self.sheet, state='readonly')
        self.sheet_box.grid(row=1, column=1, columnspan=2, sticky='ew')
        ttk.Label(form, text='Reference').grid(row=2, column=0, sticky='w', pady=7)
        ttk.Entry(form, textvariable=self.reference).grid(row=2, column=1, columnspan=2, sticky='ew')
        ttk.Label(form, text='First data row').grid(row=3, column=0, sticky='w', pady=7)
        ttk.Spinbox(form, from_=1, to=1048576, textvariable=self.first, width=8).grid(row=3, column=1, sticky='w')
        ttk.Label(panel, text='Publisher number: G     Publisher name: H     License number: I     Source tab stays unchanged; results go to a new tab.').pack(anchor='w', pady=(9, 14))
        tools = ttk.Frame(panel)
        tools.pack(fill='x')
        self.calibrate = ttk.Button(tools, text='Screen calibration…', command=self.edit_profile)
        self.calibrate.pack(side='left')
        self.test = ttk.Button(tools, text='Test search screen', command=lambda: self.start(test=True))
        self.test.pack(side='left', padx=8)
        self.balance_test = ttk.Button(tools, text='Read displayed balance', command=lambda: self.start(test='balance'))
        self.balance_test.pack(side='left', padx=(0, 8))
        self.recovery = ttk.Button(tools, text='Interrupted entries…', command=self.recover)
        self.recovery.pack(side='left')
        read_tools = ttk.Frame(panel)
        read_tools.pack(fill='x', pady=(6, 0))
        self.identity_test = ttk.Button(read_tools, text='Read displayed identity', command=lambda: self.start(test='identity'))
        self.identity_test.pack(side='left')
        self.payment_test = ttk.Button(read_tools, text='Check displayed payment', command=lambda: self.start(test='payment'))
        self.payment_test.pack(side='left', padx=8)
        ttk.Checkbutton(panel, text='Enable saving payments and adding a filtered results tab to the workbook',
                        variable=self.live).pack(anchor='w', pady=(17, 8))
        ttk.Label(panel, text='Unchecked = preview only: reads balances and transfers, writes a report, adds no payments.',
                  wraplength=750).pack(anchor='w')
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=14)
        self.start_button = ttk.Button(buttons, text='Start run', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(buttons, text='Stop', command=self.request_stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        ttk.Label(buttons, text='Hold Esc to stop while Remote Desktop is focused.').pack(side='left', padx=8)
        ttk.Label(panel, textvariable=self.status, wraplength=750).pack(anchor='w', pady=(0, 8))
        self.progress_label = tk.StringVar(value='Ready')
        self.progress_bar = ttk.Progressbar(panel, mode='determinate', maximum=1, value=0)
        self.progress_bar.pack(fill='x', pady=(0, 4))
        ttk.Label(panel, textvariable=self.progress_label).pack(anchor='w', pady=(0, 8))
        self.log = ScrolledText(panel, height=12, state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(150, self.poll)

    def choose_file(self):
        path = filedialog.askopenfilename(filetypes=[('Excel workbooks', '*.xlsx *.xlsm')])
        if not path:
            return
        try:
            sheets = sheet_names(path)
            self.source.set(path)
            self.sheet_box['values'] = sheets
            self.sheet.set(sheets[0] if len(sheets) == 1 else '')
            self.status.set('Select the worksheet and enter the reference. Save and close the source workbook before running.')
        except Exception as exc:
            messagebox.showerror('Cannot read workbook', str(exc), parent=self)

    def append(self, value):
        self.log.configure(state='normal')
        self.log.insert('end', value+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def set_busy(self, value):
        self.busy = value
        for button in (self.browse, self.calibrate, self.test, self.balance_test, self.identity_test, self.payment_test, self.recovery, self.start_button):
            button.configure(state='disabled' if value else 'normal')
        self.stop_button.configure(state='normal' if value else 'disabled')

    def start(self, test=False):
        if self.busy:
            return
        try:
            profile = load_profile(PROFILE)
            first = int(self.first.get())
            if not test and (not self.source.get() or not self.sheet.get() or not self.reference.get().strip()):
                raise ValueError('Choose an Excel file, a worksheet, and a reference.')
            if first < 1:
                raise ValueError('First data row must be at least 1')
        except Exception as exc:
            messagebox.showerror('Run setup', str(exc), parent=self)
            return
        settings = (self.source.get(), self.sheet.get(), first, self.reference.get(), self.live.get())
        self.stop.clear()
        self.set_busy(True)
        self.append('Click inside the Remote Desktop window, then wait. Processing starts automatically after your click.')
        self.append(('Leave the unsaved Financial Transaction dialog open. This check reads its fields and never clicks OK.' if test == 'payment' else
                     'Leave the license General tab open. This check only reads its license and publisher code.' if test == 'identity' else
                     'Leave the license Details tab open. This check only reads its Provisional Balance.' if test == 'balance'
                     else 'Leave License Manager at the search results screen. Keep this app visible on your other monitor.'))
        self.append('Smart sizing fits the remote session to this window; reading and clicks follow the detected display scale.')
        if test not in ('balance', 'identity', 'payment'):
            self.append('The Mechanical Royalty Module is maximized first, then the license sequence begins.')
        self.append('Do not move or resize remote dialogs during the run. Hold Esc to stop.')
        self.status.set('Click inside Remote Desktop, then wait. The run will start automatically. This window stays open.')
        self.progress_bar.stop()
        self.progress_bar.configure(mode='determinate', maximum=1, value=0)
        self.progress_total = 0
        self.progress_label.set('Waiting for your click in Remote Desktop…')
        import ctypes
        state = ctypes.windll.user32.GetAsyncKeyState(0x01)
        self.click_gate = RemoteClickGate(profile['window_title'], bool(state & 0x8000))
        self.waiting_for_remote = True
        self.remote_wait_job = self.after(60, lambda: self.wait_for_remote_click(settings, profile, test))

    def wait_for_remote_click(self, settings, profile, test):
        self.remote_wait_job = None
        if not self.waiting_for_remote:
            return
        import ctypes
        from .desktop import foreground
        if self.stop.is_set() or ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
            self.request_stop()
            return
        try:
            _, title, _ = foreground()
            state = ctypes.windll.user32.GetAsyncKeyState(0x01)
            clicked = self.click_gate.update(title, bool(state & 0x8000), bool(state & 1))
        except Exception as exc:
            self.waiting_for_remote = False
            self.set_busy(False)
            self.status.set(f'Could not detect Remote Desktop: {exc}')
            return
        if clicked:
            self.waiting_for_remote = False
            self.status.set('Remote Desktop selected. Processing—please wait and leave the mouse and keyboard alone.')
            self.progress_bar.configure(mode='indeterminate')
            self.progress_bar.start(12)
            self.progress_label.set('Checking License Manager…' if test else 'Preparing workbook…')
            self.append('Remote Desktop click detected. Starting '+('screen test.' if test else 'run.'))
            threading.Thread(target=self.worker, args=(settings, profile, test), daemon=True).start()
            return
        self.remote_wait_job = self.after(60, lambda: self.wait_for_remote_click(settings, profile, test))

    def worker(self, settings, profile, test):
        from .desktop import RemoteDriver
        from .engine import run
        log = lambda message: self.messages.put(('log', message))
        try:
            def driver_factory():
                return RemoteDriver(profile, self.stop, log)
            if test == 'payment':
                from .rules import money
                reference = settings[3].strip()
                if not reference:
                    raise ValueError('Enter the expected Reference before checking the displayed payment.')
                driver = driver_factory()
                driver.module_prepared = True
                amount = money(driver.text(driver.expect('entry'), 'entry_amount'))
                driver.verify_payment_fields(amount, reference)
                result = f'Payment field check passed: displayed amount {amount:.2f}, reference {reference!r}. Two fresh screenshots agree. No save click was sent.'
            elif test == 'identity':
                from .identity_ocr import read_identity
                driver = driver_factory()
                driver.module_prepared = True
                values = []
                for _ in range(2):
                    image = driver.expect('general')
                    values.append((read_identity(driver.ocr, driver.crop(image, 'general_license'), 'license'),
                                   read_identity(driver.ocr, driver.crop(image, 'general_publisher'), 'publisher_number')))
                    driver.wait(.5)
                if values[0] != values[1]:
                    raise ValueError(f'Opened identity changed across screenshots: {values!r}')
                result = f'Identity check passed: license {values[0][0]}, publisher {values[0][1]}. Two fresh screenshots agree. No payments or workbook changes made.'
            elif test == 'balance':
                driver = driver_factory()
                driver.module_prepared = True  # A read-only check of the already open Details tab.
                value = driver.balance('details', 'details_balance')
                result = f'Provisional Balance: {value:.2f}. Read-only check passed; no entries or workbook changes made.'
            elif test:
                driver = driver_factory()
                image = driver.expect('manager')
                log('Search screen recognized. Search value: '+driver.text(image, 'search_value'))
                for key in ('result_licenses', 'result_publishers'):
                    lines = driver.ocr.lines(driver.crop(image, key))
                    log(key+': '+repr([line.text for line in lines[:10]]))
                rows = driver.table(image, 'result_licenses', 'result_publisher_numbers')
                log('Search candidate license / publisher code rows: '+repr([(a.text,b.text) for a,b in rows]))
                if any(not code.text for _,code in rows):
                    log('Blank grid codes are unverified; the run checks each candidate in Properties before any financial action.')
                result = 'Screen test passed. Run a preview before enabling payments.'
            else:
                progress = lambda completed, total, detail: self.messages.put(('progress', (completed, total, detail)))
                folder = run(*settings[:4], settings[4], ROOT/'runs', driver_factory, self.stop, log, progress=progress)
                import csv
                with (folder/'errors.csv').open(encoding='utf-8-sig', newline='') as errors_file:
                    error_rows = list(csv.DictReader(errors_file))
                error_count = len(error_rows)
                result = (f'Live run complete. Results tab saved in {settings[0]}.' if settings[4] else 'Preview complete.')
                result += f' {error_count} row(s) need review; marked blue in '+('the results tab and recovery workbook.' if settings[4] else 'the recovery workbook.')+f' Errors: {folder / "errors.csv"}'
                if error_rows:
                    self.messages.put(('run_errors', (str(folder/'errors.csv'), error_rows)))
            self.messages.put(('done', result))
        except Exception as exc:
            self.messages.put(('error', str(exc) or type(exc).__name__))

    def poll(self):
        try:
            while True:
                kind, message = self.messages.get_nowait()
                if kind == 'run_errors':
                    path, errors = message
                    dialog = tk.Toplevel(self)
                    dialog.transient(self)
                    dialog.title(f'Run complete — {len(errors)} rows need review')
                    dialog.geometry('850x500')
                    ttk.Label(dialog, text='These rows were retained and highlighted blue.\nError report: '+path,
                              wraplength=800, padding=12).pack(anchor='w')
                    text = ScrolledText(dialog, wrap='word', font=('Consolas', 10))
                    text.pack(fill='both', expand=True, padx=12, pady=(0,12))
                    for error in errors:
                        text.insert('end', f"Excel row {error['Original Excel row']}: {error['License']} / {error['Publisher code']}\n{error['Error']}\n\n")
                    text.configure(state='disabled')
                    continue
                if kind == 'progress':
                    completed, total, detail = message
                    self.progress_total = total
                    self.progress_bar.stop()
                    self.progress_bar.configure(mode='determinate', maximum=max(1, total), value=completed)
                    percent = round(100*completed/total) if total else 0
                    self.progress_label.set(f'{completed} of {total} rows processed ({percent}%)')
                    self.status.set(detail)
                    continue
                self.append(message)
                if kind in {'done', 'error'}:
                    self.progress_bar.stop()
                    if kind == 'done':
                        self.progress_bar.configure(mode='determinate', maximum=max(1, self.progress_total), value=max(1, self.progress_total))
                        self.progress_label.set(f'Complete—{self.progress_total} rows processed' if self.progress_total else 'Screen test complete')
                    else:
                        self.progress_label.set('Stopped—see the message below and run report for details')
                    self.set_busy(False)
                    self.status.set(message)
                    self.deiconify()
                    if kind == 'error':
                        messagebox.showerror('Run stopped', message, parent=self)
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def request_stop(self):
        self.stop.set()
        if self.waiting_for_remote:
            self.waiting_for_remote = False
            if self.remote_wait_job is not None:
                self.after_cancel(self.remote_wait_job)
                self.remote_wait_job = None
            self.set_busy(False)
            self.progress_bar.stop()
            self.progress_label.set('Cancelled before processing started')
            self.status.set('Run cancelled. No processing was started.')
            self.append('Cancelled while waiting for the Remote Desktop click.')
            return
        self.status.set('Stopping after the current check…')

    def close(self):
        if self.busy:
            self.request_stop()
            self.append('Wait for the run to stop before closing this window.')
        else:
            self.destroy()

    def edit_profile(self):
        Calibration(self)

    def recover(self):
        import sqlite3
        path = ROOT/'runs'/'journal.sqlite3'
        if not path.exists():
            messagebox.showinfo('Interrupted entries', 'No run journal exists yet.', parent=self)
            return
        with sqlite3.connect(path) as db:
            pending = db.execute("SELECT license,publisher,reference,amount FROM entries WHERE status='pending'").fetchall()
        if not pending:
            messagebox.showinfo('Interrupted entries', 'There are no unfinished saves.', parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title('Resolve interrupted entries')
        ttk.Label(dialog, text='First close any unfinished dialogs in License Manager and reopen this license’s Financials.\n'
                  'Check the Type, amount and reference there before choosing a resolution below.',
                  padding=12).pack(anchor='w')
        tree = ttk.Treeview(dialog, columns=('license', 'publisher', 'reference', 'amount'), show='headings', height=8)
        for key, width in [('license', 120), ('publisher', 240), ('reference', 240), ('amount', 90)]:
            tree.heading(key, text=key.title())
            tree.column(key, width=width)
        for index, row in enumerate(pending):
            tree.insert('', 'end', iid=str(index), values=row)
        tree.pack(padx=12, pady=6)

        def resolve(saved):
            selected = tree.selection()
            if len(selected) != 1:
                return
            row = pending[int(selected[0])]
            action = 'mark this entry completed' if saved else 'allow this entry to be retried'
            if not messagebox.askyesno('Confirm manual verification',
                    f'You checked license {row[0]}, publisher {row[1]}, reference {row[2]}, amount {row[3]} in License Manager.\n\n'
                    f'The entry is {"saved" if saved else "not saved"}. Do you want to {action}?', parent=dialog):
                return
            with sqlite3.connect(path) as db:
                if saved:
                    db.execute("UPDATE entries SET status='paid', detail='User verified saved after interruption' WHERE license=? AND publisher=? AND reference=? AND status='pending'", row[:3])
                else:
                    db.execute("DELETE FROM entries WHERE license=? AND publisher=? AND reference=? AND status='pending'", row[:3])
            tree.delete(selected[0])
            self.append(f'Interrupted entry resolved by operator: {row[0]} / {row[1]} — '+('saved' if saved else 'not saved; retry enabled'))

        buttons = ttk.Frame(dialog, padding=12)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Verified saved — mark complete', command=lambda: resolve(True)).pack(side='left')
        ttk.Button(buttons, text='Verified not saved — allow retry', command=lambda: resolve(False)).pack(side='left', padx=8)


class Calibration(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title('Screen calibration — points and reading regions')
        self.profile = copy.deepcopy(load_profile(PROFILE))
        self.image = None
        self.scale = 1
        self.start_point = None
        self.mark = None
        self.updated = set()
        self.note = tk.StringVar(value='The initial layout comes from your demonstration. Capture a step only if its fields need adjusting.')
        ttk.Label(self, textvariable=self.note, wraplength=1150).pack(anchor='w', padx=14, pady=8)
        controls = ttk.Frame(self, padding=8)
        controls.pack(fill='x')
        ttk.Button(controls, text='Capture Remote Desktop in 5 seconds', command=self.capture).pack(side='left')
        ttk.Button(controls, text='Save calibration', command=self.save).pack(side='left', padx=8)
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True)
        self.fields = [(section, key) for section in ('regions', 'points') for key in self.profile[section]]
        self.list = tk.Listbox(body, width=34, height=30, exportselection=False)
        self.list.pack(side='left', fill='y', padx=8, pady=8)
        for section, key in self.fields:
            self.list.insert('end', ('Box: ' if section == 'regions' else 'Click: ')+key)
        self.list.bind('<<ListboxSelect>>', self.show_selection)
        self.canvas = tk.Canvas(body, width=1000, height=650, bg='#20252c', cursor='crosshair')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self.begin)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.finish)
        self.list.selection_set(0)
        ttk.Label(self, text='Open each corresponding screen yourself. Capture it, select a field, then drag its reading box or click its button center.\n'
                  'Table column boxes must cover only data rows and share the same top and bottom. Keep the last column fully visible.\n'
                  'Calibration never clicks the remote application or saves financial entries. Cancel any test entry yourself when finished.',
                  wraplength=1250).pack(anchor='w', padx=14, pady=10)

    def capture(self):
        self.withdraw()
        self.parent.withdraw()
        self.after(5000, self.grab)

    def grab(self):
        from .desktop import capture_remote, foreground
        from PIL import ImageTk
        try:
            _, title, rect = foreground()
            if title != self.profile['window_title']:
                raise ValueError('Focus the Remote Desktop window during the countdown.')
            raw, _, _ = capture_remote(self.profile)
            from .tracking import ToolbarTracker
            self.image = ToolbarTracker().locate(raw).normalize(raw, self.profile['window_size'])
            self.scale = min(1100/self.image.width, 700/self.image.height, 1)
            display = self.image.resize((round(self.image.width*self.scale), round(self.image.height*self.scale)))
            self.photo = ImageTk.PhotoImage(display)
            self.canvas.configure(width=display.width, height=display.height)
            self.canvas.delete('all')
            self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
            self.mark = None
            self.show_selection()
        except Exception as exc:
            messagebox.showerror('Capture failed', str(exc), parent=self.parent)
        finally:
            self.parent.deiconify()
            self.deiconify()

    def selected(self):
        indexes = self.list.curselection()
        return self.fields[indexes[0]] if indexes else None

    def show_selection(self, *_):
        selected = self.selected()
        if not selected:
            return
        section, key = selected
        self.note.set(f'{key}: '+('Drag a rectangle around only the text/data to read.' if section == 'regions' else 'Click the center of this button or field on the captured picture.'))
        if self.mark:
            self.canvas.delete(self.mark)
        if self.image is None:
            return
        value = [n*self.scale for n in self.profile[section][key]]
        if section == 'regions':
            self.mark = self.canvas.create_rectangle(*value, outline='#ff3636', width=2)
        else:
            x, y = value
            self.mark = self.canvas.create_oval(x-5, y-5, x+5, y+5, outline='#ff3636', width=2)

    def begin(self, event):
        if self.image is not None:
            self.start_point = (event.x, event.y)

    def drag(self, event):
        if self.image is None or self.start_point is None or self.selected()[0] != 'regions':
            return
        if self.mark:
            self.canvas.delete(self.mark)
        self.mark = self.canvas.create_rectangle(*self.start_point, event.x, event.y, outline='#ff3636', width=2)

    def finish(self, event):
        if self.image is None or self.start_point is None:
            return
        section, key = self.selected()
        x, y = (round(event.x/self.scale), round(event.y/self.scale))
        if section == 'regions':
            x0, y0 = (round(n/self.scale) for n in self.start_point)
            value = [min(x, x0), min(y, y0), max(x, x0), max(y, y0)]
            if value[2]-value[0] < 4 or value[3]-value[1] < 4:
                return
        else:
            value = [x, y]
        self.profile[section][key] = value
        self.updated.add((section, key))
        self.start_point = None
        self.show_selection()

    def save(self):
        try:
            PROFILE.parent.mkdir(exist_ok=True)
            temp = PROFILE.with_suffix('.tmp.json')
            temp.write_text(json.dumps(self.profile, indent=2), encoding='utf-8')
            load_profile(temp)
            temp.replace(PROFILE)
            self.parent.append('Calibration saved. Test the search screen and run a preview.')
            self.destroy()
        except Exception as exc:
            messagebox.showerror('Cannot save calibration', str(exc), parent=self)


def main():
    initialize_data()
    App().mainloop()
