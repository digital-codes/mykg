def test_import_mykg_has_no_side_effects(monkeypatch):
    """Importing mykg must not call load_dotenv or setup the root logger."""
    import logging
    import sys

    # Save and remove cached mykg modules so we get a fresh import.
    # monkeypatch.setitem restores each entry after the test — this prevents
    # test_init from leaving orphaned module objects that cause class-identity
    # mismatches in later tests (e.g. two copies of SchemaUpdatedError).
    saved = {k: v for k, v in sys.modules.items() if k.startswith("mykg")}
    for key in saved:
        monkeypatch.delitem(sys.modules, key)

    root_handlers_before = len(logging.getLogger().handlers)

    import mykg  # noqa: F401

    root_handlers_after = len(logging.getLogger().handlers)
    assert root_handlers_after == root_handlers_before, (
        f"import mykg added {root_handlers_after - root_handlers_before} root logger handler(s)"
    )
