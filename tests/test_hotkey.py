import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mywhisper.dictation.hotkey import (
    MOD_ALT,
    MOD_CTRL,
    MOD_SHIFT,
    MOD_WIN,
    VK_ESCAPE,
    HotkeyMatcher,
    KeyboardHook,
    parse_hotkey,
)

VK_SPACE, VK_D = 0x20, 0x44


@pytest.mark.parametrize(
    ("text", "vk", "mods"),
    [
        ("Ctrl+Shift+Space", VK_SPACE, MOD_CTRL | MOD_SHIFT),
        ("Ctrl+Alt+D", VK_D, MOD_CTRL | MOD_ALT),
        ("Meta+F9", 0x78, MOD_WIN),
        ("F9", 0x78, 0),
        ("Pause", 0x13, 0),
        ("Ctrl+5", 0x35, MOD_CTRL),
    ],
)
def test_parse_hotkey(text, vk, mods):
    hotkey = parse_hotkey(text)
    assert (hotkey.vk, hotkey.mods) == (vk, mods)


@pytest.mark.parametrize("text", ["", "Ctrl+Shift+Space, F1", "Space", "A", "Ctrl+Escape", "nimporte quoi+"])
def test_parse_hotkey_rejects(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)


def test_matcher_press_release_and_autorepeat():
    m = HotkeyMatcher(parse_hotkey("Ctrl+Shift+Space"))
    both = MOD_CTRL | MOD_SHIFT
    assert m.feed(VK_SPACE, True, both) == ("press", True)
    assert m.feed(VK_SPACE, True, both) == (None, True)  # auto-repeat swallowed
    # modifiers released first: the release still ends the dictation
    assert m.feed(VK_SPACE, False, 0) == ("release", True)
    assert m.feed(VK_SPACE, False, 0) == (None, False)


def test_matcher_ignores_other_combinations():
    m = HotkeyMatcher(parse_hotkey("Ctrl+Shift+Space"))
    assert m.feed(VK_SPACE, True, 0) == (None, False)  # plain space types normally
    assert m.feed(VK_SPACE, True, MOD_CTRL) == (None, False)
    assert m.feed(VK_SPACE, True, MOD_CTRL | MOD_SHIFT | MOD_ALT) == (None, False)
    assert m.feed(VK_D, True, MOD_CTRL | MOD_SHIFT) == (None, False)


def test_escape_only_while_armed():
    m = HotkeyMatcher(parse_hotkey("F9"))
    assert m.feed(VK_ESCAPE, True, 0) == (None, False)
    m.escape_armed = True
    assert m.feed(VK_ESCAPE, True, 0) == ("escape", True)
    assert m.feed(VK_ESCAPE, False, 0) == (None, False)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class FakeUser32:
    def __init__(self):
        self.next_handle = 100
        self.installed = []
        self.fail = False

    def SetWindowsHookExW(self, kind, proc, module, thread):
        if self.fail:
            return 0
        self.next_handle += 1
        self.installed.append(self.next_handle)
        return self.next_handle

    def UnhookWindowsHookEx(self, handle):
        self.installed.remove(handle)
        return True


def test_hook_is_reinstalled_without_gap(qapp):
    user32 = FakeUser32()
    hook = KeyboardHook(user32=user32)
    hook.set_hotkey(parse_hotkey("Ctrl+Shift+Space"))
    assert hook.install() and user32.installed == [101]
    hook.reinstall()
    assert user32.installed == [102]  # the new one replaced the old one

    hook._matcher.feed(0x20, True, MOD_CTRL | MOD_SHIFT)  # hotkey held: no swap now
    hook.reinstall()
    assert user32.installed == [102]
    hook._matcher.feed(0x20, False, MOD_CTRL | MOD_SHIFT)

    user32.fail = True
    hook.reinstall()  # a failed attempt keeps the current hook
    assert user32.installed == [102]
    hook.uninstall()
    assert user32.installed == [] and not hook._watchdog.isActive()
