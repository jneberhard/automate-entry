from types import SimpleNamespace
from threading import Event
from royalty_entry.gui import App


class Value:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Bar:
    def __init__(self):
        self.options = {}
        self.running = False

    def configure(self, **options):
        self.options.update(options)

    def start(self, *_):
        self.running = True

    def stop(self):
        self.running = False


def setup_app(monkeypatch):
    from royalty_entry import gui
    profile = {'window_title': 'Remote Desktop'}
    monkeypatch.setattr(gui, 'load_profile', lambda _: profile)
    mouse_state = Value(0)
    import ctypes
    monkeypatch.setattr(ctypes.windll.user32, 'GetAsyncKeyState', lambda key: mouse_state.get() if key == 1 else 0)
    from royalty_entry import desktop
    foreground_title = Value('Royalty Entry')
    monkeypatch.setattr(desktop, 'foreground', lambda: (1, foreground_title.get(), (0, 0, 100, 100)))
    scheduled, logs, workers = [], [], []
    fake = SimpleNamespace(busy=False, source=Value('source.xlsx'), sheet=Value('Payments'),
                           first=Value('2'), reference=Value('Q3'), live=Value(False), stop=Event(),
                           status=Value(), progress_label=Value(), progress_bar=Bar(), progress_total=0,
                           append=logs.append, after=lambda delay, callback: scheduled.append((delay, callback)),
                           after_cancel=lambda job: None, worker=lambda *args: None)
    fake.set_busy = lambda value: setattr(fake, 'busy', value)
    fake.wait_for_remote_click = lambda *args: App.wait_for_remote_click(fake, *args)
    fake.request_stop = lambda: App.request_stop(fake)
    # No iconify method exists: a regression that hides the app fails this test.
    class Thread:
        def __init__(self, target, args, daemon):
            self.args = args

        def start(self):
            workers.append(self.args)

    monkeypatch.setattr(gui.threading, 'Thread', Thread)
    return fake, profile, mouse_state, foreground_title, scheduled, workers


def test_start_keeps_window_visible_and_waits_until_remote_click(monkeypatch):
    app, profile, mouse, title, scheduled, workers = setup_app(monkeypatch)
    App.start(app)
    assert app.busy and app.waiting_for_remote
    assert 'Click inside Remote Desktop' in app.status.get()
    assert scheduled[0][0] == 60  # Monitor input, never launch from a fixed countdown.
    assert not workers
    title.set('Remote Desktop')
    App.wait_for_remote_click(app, (), profile, False)
    assert not workers  # Focus alone is insufficient.
    mouse.set(1)  # A complete short click occurred since the preceding poll.
    App.wait_for_remote_click(app, (), profile, False)
    assert len(workers) == 1
    assert not app.waiting_for_remote
    assert app.progress_bar.running


def test_stop_while_waiting_never_starts_worker(monkeypatch):
    app, profile, mouse, title, scheduled, workers = setup_app(monkeypatch)
    App.start(app)
    App.request_stop(app)
    title.set('Remote Desktop')
    mouse.set(1)
    App.wait_for_remote_click(app, (), profile, False)
    assert not workers and not app.busy
    assert app.stop.is_set()
    assert 'No processing was started' in app.status.get()
