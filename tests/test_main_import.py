def test_mcp_server_importable():
    from server.main import mcp

    assert mcp.name
