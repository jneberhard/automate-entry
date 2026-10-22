"""Wait for an explicit mouse click in the selected Remote Desktop window."""


class RemoteClickGate:
    def __init__(self, title, mouse_down=False):
        self.title = title
        # Ignore the Start button press, even if it is still held when we arm.
        self.await_initial_release = mouse_down
        self.pending = False
        self.was_down = mouse_down

    def update(self, title, mouse_down, pressed_since_poll=False):
        if self.await_initial_release:
            self.await_initial_release = mouse_down
            self.was_down = mouse_down
            return False
        pressed = pressed_since_poll or (mouse_down and not self.was_down)
        self.was_down = mouse_down
        if title != self.title:
            self.pending = False
            return False
        if pressed:
            self.pending = True
        if self.pending and not mouse_down:
            self.pending = False
            return True
        return False
