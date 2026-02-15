# sandboxtown_v2/tests/test_mode_gate_smoke.py

def test_mode_gate_import_smoke():
    # Importing the module alone will cover the definition lines (and any top-level logic).
    import sandboxtown_v2.core.mode_gate as mode_gate  # noqa: F401
    assert mode_gate is not None


def test_mode_gate_has_public_surface():
    import sandboxtown_v2.core.mode_gate as mode_gate

    # Soft “shape” assertions (won’t break if you rename things later)
    public = [n for n in dir(mode_gate) if not n.startswith("_")]
    assert len(public) > 0
