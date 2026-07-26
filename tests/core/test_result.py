from freecad_mcp.core.result import CommandResult


def test_success_result_defaults_to_empty_data() -> None:
    result = CommandResult.success("example.ok", "Completed")

    assert result.ok is True
    assert result.data == {}


def test_failure_result_keeps_structured_data() -> None:
    result = CommandResult.failure("example.failed", "Failed", {"field": "name"})

    assert result.ok is False
    assert result.data == {"field": "name"}


def test_results_serialize_for_mcp_and_report_view() -> None:
    success = CommandResult.success("example.ok", "Completed", {"value": 42})
    failure = CommandResult.failure("example.failed", "Failed", {"field": "name"})

    assert success.to_dict() == {"ok": True, "value": 42, "message": "Completed"}
    assert failure.to_dict() == {
        "ok": False,
        "error": {
            "code": "example.failed",
            "message": "Failed",
            "details": {"field": "name"},
        },
    }
