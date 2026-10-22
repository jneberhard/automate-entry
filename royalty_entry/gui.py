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


ROOT = data_root()
PROFILE = ROOT / 'calibration' / 'profile.json'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Royalty Entry — Remote Desktop')
        icon = asset_root() / 'assets' / 'royalty-entry.ico'
        if icon.exists():
            self.iconbitmap(str(icon))
        self.geometry('820x720')
        self.minsize(760, 660)
        self.option_add('*Font', '{Segoe UI} 10')
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
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
        ttk.Label(panel, text='Publisher: column H     License number: column I     Original workbook stays unchanged.').pack(anchor='w', pady=(9, 14))
        tools = ttk.Frame(panel)
        tools.pack(fill='x')
        self.calibrate = ttk.Button(tools, text='Screen calibration…', command=self.edit_profile)
        self.calibrate.pack(side='left')
        self.test = ttk.Button(tools, text='Test search screen', command=lambda: self.start(test=True))
        self.test.pack(side='left', padx=8)
        self.recovery = ttk.Button(tools, text='Interrupted entries…', command=self.recover)
        self.recovery.pack(side='left')
        ttk.Checkbutton(panel, text='Enable saving payments and removing rejected rows in the workbook copy',
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
        for button in (self.browse, self.calibrate, self.test, self.recovery, self.start_button):
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
        self.append('Switch to Remote Desktop within 6 seconds. Leave License Manager at the search results screen.')
        self.append('Do not move or resize remote dialogs during the run. Hold Esc to stop.')
        self.status.set('Starting in 6 seconds…')
        self.iconify()
        self.after(6000, lambda: threading.Thread(target=self.worker, args=(settings, profile, test), daemon=True).start())

    def worker(self, settings, profile, test):
        from .desktop import RemoteDriver
        from .engine import run
        log = lambda message: self.messages.put(('log', message))
        try:
            def driver_factory():
                return RemoteDriver(profile, self.stop, log)
            if test:
                driver = driver_factory()
                image = driver.expect('manager')
                log('Search screen recognized. Search value: '+driver.text(image, 'search_value'))
                result = 'Screen test passed. Run a preview before enabling payments.'
            else:
                folder = run(*settings[:4], settings[4], ROOT/'runs', driver_factory, self.stop, log)
                result = f'{"Live run" if settings[4] else "Preview"} complete. Results: {folder}'
            self.messages.put(('done', result))
        except Exception as exc:
            self.messages.put(('error', str(exc) or type(exc).__name__))

    def poll(self):
        try:
            while True:
                kind, message = self.messages.get_nowait()
                self.append(message)
                if kind in {'done', 'error'}:
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
        self.dirty_size = False
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
            size = [rect[2]-rect[0], rect[3]-rect[1]]
            if size != self.profile['window_size']:
                self.dirty_size = True
                self.profile['window_size'] = size
            self.image, _, _ = capture_remote(self.profile)
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
        if self.dirty_size and len(self.updated) != len(self.fields):
            messagebox.showerror('Finish calibration', 'The window size changed. Set every field across all six screens before saving, or restore the original size.', parent=self)
            return
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
