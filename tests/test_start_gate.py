from royalty_entry.start_gate import RemoteClickGate


def test_changing_focus_without_click_does_not_start():
    gate = RemoteClickGate('Remote Desktop')
    assert not gate.update('Royalty Entry', False)
    assert not gate.update('Remote Desktop', False)
    assert not gate.update('Remote Desktop', False)


def test_click_starts_only_after_release_in_remote_window():
    gate = RemoteClickGate('Remote Desktop')
    assert not gate.update('Remote Desktop', True)
    assert not gate.update('Remote Desktop', True)
    assert gate.update('Remote Desktop', False)
    assert not gate.update('Remote Desktop', False)


def test_short_click_between_polls_is_detected():
    gate = RemoteClickGate('Remote Desktop')
    assert gate.update('Remote Desktop', False, pressed_since_poll=True)


def test_start_button_press_cannot_trigger_the_run():
    gate = RemoteClickGate('Remote Desktop', mouse_down=True)
    assert not gate.update('Remote Desktop', True, pressed_since_poll=True)
    assert not gate.update('Remote Desktop', False)
    assert not gate.update('Remote Desktop', False)
    assert gate.update('Remote Desktop', False, pressed_since_poll=True)


def test_click_in_other_window_does_not_start_on_later_focus_change():
    gate = RemoteClickGate('Remote Desktop')
    assert not gate.update('Excel', True, pressed_since_poll=True)
    assert not gate.update('Excel', False)
    assert not gate.update('Remote Desktop', False)


def test_focus_loss_before_release_cancels_click():
    gate = RemoteClickGate('Remote Desktop')
    assert not gate.update('Remote Desktop', True)
    assert not gate.update('Excel', False)
    assert not gate.update('Remote Desktop', False)
