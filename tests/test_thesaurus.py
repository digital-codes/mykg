from mykg.thesaurus import parse_thesaurus

SKOS_TTL = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex:   <http://example.org/> .

ex:MLModel skos:exactMatch ex:MachineLearningModel .
ex:Org     skos:closeMatch ex:Organisation .
ex:Person  skos:broader    ex:Agent .
"""


def test_parse_returns_term_count():
    idx = parse_thesaurus(SKOS_TTL)
    assert idx.term_count >= 3


def test_exact_match_detected():
    idx = parse_thesaurus(SKOS_TTL)
    assert idx.is_exact("MLModel", "MachineLearningModel")
    assert idx.is_exact("MachineLearningModel", "MLModel")


def test_close_match_detected():
    idx = parse_thesaurus(SKOS_TTL)
    assert idx.is_close("Org", "Organisation")
    assert idx.is_close("Organisation", "Org")


def test_broader_is_not_exact_or_close():
    idx = parse_thesaurus(SKOS_TTL)
    assert not idx.is_exact("Person", "Agent")
    assert not idx.is_close("Person", "Agent")


def test_unknown_terms_return_false():
    idx = parse_thesaurus(SKOS_TTL)
    assert not idx.is_exact("Foo", "Bar")
    assert not idx.is_close("Foo", "Bar")
