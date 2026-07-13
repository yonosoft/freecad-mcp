from freecad_mcp.application import create_application


def test_application_dispatches_status_command() -> None:
    result = create_application().report_status()

    assert result.ok is True
    assert result.code == "workbench.status.ok"
    assert result.data["mcp_server_running"] is False
