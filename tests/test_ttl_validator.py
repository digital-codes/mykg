from mykg.ttl_validator import validate_knowledge_graph_ttl

VALID_TTL = """\
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://mykg.local/schema/> .
@prefix data: <http://mykg.local/data/> .

ex:Person       rdf:type rdfs:Class .
ex:Organization rdf:type rdfs:Class .

ex:name rdf:type rdf:Property ;
    rdfs:domain ex:Person ;
    rdfs:range  rdfs:Literal .

ex:works_at rdf:type rdf:Property ;
    rdfs:domain ex:Person ;
    rdfs:range  ex:Organization .

data:alice   rdf:type ex:Person .
data:acme    rdf:type ex:Organization .
data:alice   ex:name "Alice" .
data:alice   ex:works_at data:acme .
"""

UNDECLARED_TYPE_TTL = """\
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://mykg.local/schema/> .
@prefix data: <http://mykg.local/data/> .

ex:Person rdf:type rdfs:Class .

data:alice rdf:type ex:Ghost .
"""


def test_valid_ttl_passes():
    result = validate_knowledge_graph_ttl(VALID_TTL)
    assert result["valid"] is True
    assert result["abox_checks"]["errors"] == []


def test_undeclared_type_fails():
    result = validate_knowledge_graph_ttl(UNDECLARED_TYPE_TTL)
    assert result["valid"] is False
    assert any("Ghost" in e["message"] for e in result["abox_checks"]["errors"])


def test_result_always_has_tbox_and_abox():
    result = validate_knowledge_graph_ttl(VALID_TTL)
    assert "tbox_checks" in result
    assert "abox_checks" in result
    assert "errors" in result["tbox_checks"]
    assert "errors" in result["abox_checks"]
