from claude_handoff_web import hello


def test_hello() -> None:
    assert hello("world") == "Hello, world!"
