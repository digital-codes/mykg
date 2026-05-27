from mykg.schema_flattener import flatten_schema

SCHEMA = {
    "concepts": [
        {"type": "Person", "parent": None, "attributes": ["name", "email", "birth_date"]},
        {
            "type": "SoftwareEngineer",
            "parent": "Person",
            "attributes": ["programming_languages", "seniority"],
        },
        {"type": "Organization", "parent": None, "attributes": ["name", "industry"]},
    ],
    "properties": [],
}


def test_root_concept_flat_is_own_attrs():
    result = flatten_schema(SCHEMA)
    assert result["Person"] == ["name", "email", "birth_date"]


def test_child_concept_inherits_parent_attrs():
    result = flatten_schema(SCHEMA)
    flat = result["SoftwareEngineer"]
    assert "name" in flat
    assert "email" in flat
    assert "birth_date" in flat
    assert "programming_languages" in flat
    assert "seniority" in flat


def test_child_parent_attrs_come_first():
    result = flatten_schema(SCHEMA)
    flat = result["SoftwareEngineer"]
    # root attrs before own attrs
    assert flat.index("name") < flat.index("programming_languages")


def test_unrelated_concept_not_affected():
    result = flatten_schema(SCHEMA)
    assert result["Organization"] == ["name", "industry"]
    assert "email" not in result["Organization"]


def test_all_concepts_present():
    result = flatten_schema(SCHEMA)
    assert set(result.keys()) == {"Person", "SoftwareEngineer", "Organization"}


def test_flatten_one_cycle_does_not_infinite_loop():
    """A cyclic is-a chain must not loop forever — return partial attrs and log a warning."""
    schema = {
        "concepts": [
            {"type": "A", "parent": "B", "attributes": ["x"]},
            {"type": "B", "parent": "A", "attributes": ["y"]},
        ]
    }
    # Must complete without hanging
    result = flatten_schema(schema)
    # Both A and B should have some attributes — exact set depends on traversal order
    assert set(result["A"]).issubset({"x", "y"})
    assert set(result["B"]).issubset({"x", "y"})
