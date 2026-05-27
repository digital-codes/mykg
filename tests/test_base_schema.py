import pytest

from mykg.base_schema import BaseSchemaError, parse_base_schema

VALID_TTL = """\
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://mykg.local/schema/> .

ex:Vehicle    rdf:type rdfs:Class .
ex:ElectricCar rdf:type rdfs:Class .
ex:ElectricCar rdfs:subClassOf ex:Vehicle .

ex:name rdf:type rdf:Property ;
    rdfs:domain ex:Vehicle ;
    rdfs:range  rdfs:Literal .

ex:manufactured_by rdf:type rdf:Property ;
    rdfs:domain ex:Vehicle ;
    rdfs:range  ex:Manufacturer .

ex:Manufacturer rdf:type rdfs:Class .
"""

INVALID_TTL = "not turtle at all %%"


def test_parse_valid_ttl_returns_classes():
    result = parse_base_schema(VALID_TTL)
    assert "Vehicle" in result["locked_classes"]
    assert "ElectricCar" in result["locked_classes"]
    assert "Manufacturer" in result["locked_classes"]


def test_parse_valid_ttl_class_parent():
    result = parse_base_schema(VALID_TTL)
    assert result["locked_classes"]["ElectricCar"]["parent"] == "Vehicle"
    assert result["locked_classes"]["Vehicle"]["parent"] is None


def test_parse_valid_ttl_class_attributes():
    result = parse_base_schema(VALID_TTL)
    assert "name" in result["locked_classes"]["Vehicle"]["attributes"]


def test_parse_valid_ttl_object_property():
    result = parse_base_schema(VALID_TTL)
    assert "manufactured_by" in result["locked_properties"]
    prop = result["locked_properties"]["manufactured_by"]
    assert prop["domain"] == "Vehicle"
    assert prop["range"] == "Manufacturer"


def test_parse_invalid_ttl_raises():
    with pytest.raises(BaseSchemaError):
        parse_base_schema(INVALID_TTL)
