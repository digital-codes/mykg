import pytest

from mykg.llm.adapter import LLMAdapter


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        LLMAdapter()


def test_adapter_complete_raises_not_implemented():
    class Concrete(LLMAdapter):
        pass

    with pytest.raises(TypeError):
        Concrete()


def test_concrete_adapter_works():
    class Echo(LLMAdapter):
        def complete(
            self,
            system: str,
            user: str,
            context_label: str = "",
            max_tokens: int | None = None,
            timeout: int | None = None,
        ) -> str:
            return f"system={system} user={user}"

        def endpoint_label(self) -> str:
            return "echo"

    adapter = Echo()
    result = adapter.complete("sys", "usr")
    assert result == "system=sys user=usr"
