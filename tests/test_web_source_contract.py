"""Static web-source checks; these are not rendered-browser verification."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_static_accessible_name_contract_is_present():
    task = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for required in (
        'aria-label="Channels"',
        'id="channel-chat"',
        'aria-label="Chat options"',
        'aria-label="Theme: follow system"',
        '<span>New automation</span>',
        'aria-label="Close editor"',
        'aria-label="Day of the week"',
        'aria-label="Time of day"',
        'aria-label="Minutes past the hour"',
        'aria-label="Attach a file"',
        'aria-label="Message Agentonomy Tasks"',
        'aria-label="Send message"',
    ):
        assert required in task
    assert 'aria-label="${esc(automation.name)} options"' in script


def test_static_keyboard_and_focus_contract_is_present_without_voice():
    task = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")

    assert 'input.addEventListener("keydown"' in script
    assert 'event.key === "Enter"' in script
    assert "!event.shiftKey" in script
    assert ".channel:focus-visible" in css
    assert ".icon-button:focus-visible" in css
    assert ".row-menu button:focus-visible" in css
    assert ".attach-button:focus-visible" in css
    assert "composer-voice" not in task + script + css
    assert "voice-button" not in task + script + css


def test_the_composer_buttons_never_leave_the_bottom_corners():
    """A wrapped message must not reflow attach, mic and send onto a new row."""
    task = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")

    assert "data-expanded" not in task + script + css
    assert "grid-template-columns: auto minmax(0, 1fr) auto auto;" in css
    assert "align-items: end;" in css


def test_the_removed_surfaces_leave_nothing_behind():
    web = ROOT / "web"
    assert not (web / "learning.html").exists()
    assert not (web / "learning.css").exists()
    assert not (web / "learning.js").exists()
    assert not (ROOT / "app" / "learning.py").exists()
    markup = (web / "index.html").read_text(encoding="utf-8")
    assert "learning" not in markup.casefold()
    # The Settings channel and its pane are gone; the word itself is free to be
    # used by whatever else lives in the editor.
    assert 'id="channel-settings"' not in markup
    assert 'id="settings-pane"' not in markup
