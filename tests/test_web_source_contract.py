"""Static web-source checks; these are not rendered-browser verification."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_static_accessible_name_contract_is_present():
    task = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    learning = (ROOT / "web" / "learning.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for required in (
        'aria-label="Product navigation"',
        '>Home</a>',
        'aria-label="Toggle theme"',
        '>Run now</button>',
        'aria-label="Attach a file"',
        'aria-label="Message Avi\'s assistant"',
        'aria-label="Send message"',
    ):
        assert required in task
    for required in (
        'aria-label="Learning navigation"',
        '>Task Chat</a>',
        'aria-label="Learning period"',
        '>Day</button>',
        '>Week</button>',
        '>Month</button>',
    ):
        assert required in learning
    assert 'aria-label", "Choose tomorrow\'s plan"' in script
    assert "button.textContent = control.label" in script
    assert "runNow.setAttribute(\"aria-label\"" in script


def test_static_keyboard_and_focus_contract_is_present_without_voice():
    task = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
    learning_css = (ROOT / "web" / "learning.css").read_text(encoding="utf-8")

    assert 'input.addEventListener("keydown"' in script
    assert 'event.key === "Enter"' in script
    assert "!event.shiftKey" in script
    assert ".product-nav a:focus-visible" in css
    assert ".run-button:focus-visible" in css
    assert ".attach-button:focus-visible" in css
    assert ".plan-control:focus-visible" in css
    assert ".period-switch button:focus-visible" in learning_css
    assert "composer-voice" not in task + script + css
    assert "voice-button" not in task + script + css
