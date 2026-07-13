from freecad_mcp.core.result import CommandResult


def test_success_result_defaults_to_empty_data() -> None:
    result = CommandResult.success("example.ok", "Completed")

    assert result.ok is True
    assert result.data == {}


def test_failure_result_keeps_structured_data() -> None:
    result = CommandResult.failure("example.failed", "Failed", {"field": "name"})

    assert result.ok is False
    assert result.data == {"field": "name"}
