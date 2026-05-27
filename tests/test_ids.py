"""Tests for mykg.ids.stable_id — D19 stable node ID generation."""

from mykg.ids import stable_id

# ---------------------------------------------------------------------------
# Basic format
# ---------------------------------------------------------------------------


def test_basic_format():
    result = stable_id("Person", "Alice")
    assert result == "person-alice"


def test_type_lowercased():
    result = stable_id("SoftwareEngineer", "Alice")
    assert result.startswith("softwareengineer-")


def test_name_lowercased():
    result = stable_id("Person", "ALICE")
    assert result == "person-alice"


def test_name_whitespace_normalized_to_hyphens():
    result = stable_id("Organization", "Acme Corp")
    assert result == "organization-acme-corp"


def test_leading_trailing_whitespace_stripped():
    result = stable_id("Person", "  Alice  ")
    assert result == "person-alice"


def test_multiple_internal_spaces_collapsed():
    result = stable_id("Person", "Alice   B   Smith")
    assert result == "person-alice-b-smith"


# ---------------------------------------------------------------------------
# Non-alphanumeric characters in type prefix
# ---------------------------------------------------------------------------


def test_type_with_spaces_stripped():
    result = stable_id("HTTP Server", "nginx")
    assert result == "httpserver-nginx"


def test_type_with_hyphens_stripped():
    result = stable_id("Node-Type", "foo")
    assert result == "nodetype-foo"


def test_type_with_special_chars_stripped():
    result = stable_id("My.Type!", "bar")
    assert result == "mytype-bar"


# ---------------------------------------------------------------------------
# Non-alphanumeric characters in name slug
# ---------------------------------------------------------------------------


def test_name_punctuation_stripped():
    result = stable_id("Person", "O'Brien")
    assert result == "person-obrien"


def test_name_with_hyphen_stripped():
    # hyphens in the name are NOT alphanumeric — they are removed from the slug
    result = stable_id("Person", "Mary-Jane")
    assert result == "person-maryjane"


def test_name_with_numbers_preserved():
    result = stable_id("Version", "Python 3")
    assert result == "version-python-3"


# ---------------------------------------------------------------------------
# Matches assembler._stable_id exactly (regression)
# ---------------------------------------------------------------------------


def test_matches_assembler_softwareengineer_alice():
    """Must produce the ID expected by test_assembler tests."""
    assert stable_id("SoftwareEngineer", "Alice") == "softwareengineer-alice"


def test_matches_assembler_organization_acme_corp():
    assert stable_id("Organization", "Acme Corp") == "organization-acme-corp"


def test_matches_assembler_type_with_spaces():
    """Matches the explicit assertion in test_assembler.test_stable_id_type_prefix_no_spaces."""
    assert stable_id("HTTP Server", "nginx") == "httpserver-nginx"


# ---------------------------------------------------------------------------
# Result always contains exactly one hyphen separating prefix and slug
# ---------------------------------------------------------------------------


def test_result_has_hyphen_separator():
    result = stable_id("Person", "Alice")
    assert "-" in result


def test_no_spaces_in_result():
    result = stable_id("Software Engineer", "Alice Smith")
    assert " " not in result
