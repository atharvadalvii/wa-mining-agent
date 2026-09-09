import pytest

from geoagent.tools.registry import ToolSpec, dispatch, get_tool, openai_tool_schemas, register


@pytest.fixture(autouse=True)
def clean_registry():
    from geoagent.tools import registry as reg

    saved = dict(reg._REGISTRY)
    reg._REGISTRY.clear()
    yield
    reg._REGISTRY.clear()
    reg._REGISTRY.update(saved)


def test_register_and_get_tool():
    spec = ToolSpec(
        name="echo",
        description="Echoes input",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        handler=lambda text: text,
    )
    register(spec)
    assert get_tool("echo") is spec
    assert get_tool("missing") is None


def test_duplicate_register_raises():
    spec = ToolSpec(
        name="dup",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
    register(spec)
    with pytest.raises(ValueError):
        register(spec)


def test_openai_tool_schemas_shape():
    register(
        ToolSpec(
            name="foo",
            description="Does foo",
            parameters={"type": "object", "properties": {"x": {"type": "number"}}, "required": []},
            handler=lambda x=0: str(x),
        )
    )
    schemas = openai_tool_schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "foo"
    assert schema["function"]["description"] == "Does foo"
    assert schema["function"]["parameters"]["type"] == "object"


def test_dispatch_calls_handler():
    register(
        ToolSpec(
            name="add",
            description="adds",
            parameters={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
            handler=lambda a, b: str(a + b),
        )
    )
    assert dispatch("add", {"a": 1, "b": 2}) == "3"


def test_dispatch_unknown_tool_returns_error_string():
    result = dispatch("nonexistent", {})
    assert "error" in result
    assert "nonexistent" in result


def test_dispatch_handler_exception_returns_error_string():
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    register(
        ToolSpec(
            name="boom",
            description="raises",
            parameters={"type": "object", "properties": {}},
            handler=boom,
        )
    )
    result = dispatch("boom", {})
    assert "kaboom" in result
    assert "RuntimeError" in result
