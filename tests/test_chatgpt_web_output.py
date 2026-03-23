from server.tools.chatgpt_web import ChatGPTResearchOutput, _error_payload, _make_summary


def test_make_summary_short():
    assert _make_summary("hello world") == "hello world"


def test_make_summary_truncates():
    long = "x" * 600
    s = _make_summary(long)
    assert len(s) < len(long)
    assert s.endswith("…")


def test_output_model_dump():
    m = ChatGPTResearchOutput(
        summary="s",
        full_response="full",
        status="ok",
        execution_time=1.23,
        error_code=None,
        error_detail=None,
    )
    d = m.model_dump()
    assert d["status"] == "ok"
    assert d["full_response"] == "full"
    assert d["error_code"] is None


def test_error_payload_fields():
    d = _error_payload("timeout", "too slow", 2.5)
    assert d["status"] == "error"
    assert d["error_code"] == "timeout"
    assert d["error_detail"] == "too slow"
    assert "timeout" in d["summary"]
