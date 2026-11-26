"""Ask CometIQ (LangGraph): answers only from stored records, with citations, and permission-scoped."""


def _ask(client, h, q):
    r = client.post("/api/ask", headers=h, json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_ask_builtin_graph(client, tokens):
    fac = tokens["faculty"]
    syl = next(s for s in client.get("/api/gap/syllabi", headers=fac).json() if s["code"] == "BUAN 6356")
    client.post(f"/api/gap/syllabi/{syl['id']}/analyze", headers=fac, json={"target": "Data Analyst"})
    client.post(f"/api/gap/syllabi/{syl['id']}/analyze", headers=fac, json={"target": "All roles"})
    r = _ask(client, fac, "Why did BUAN 6356 drop?")
    assert r["intent"] == "score_change" and r["course"] == "BUAN 6356" and r["citations"]
    assert "points" in r["answer"] and "[1]" in r["answer"] and r["steps"][0].startswith("understand")
    assert all(c["link"].startswith("/") for c in r["citations"])
    r = _ask(client, fac, "Which priority gaps have no decision yet?")
    assert r["intent"] == "undecided_gaps" and r["citations"]
    r = _ask(client, fac, "Draft the AACSB summary for SQL.")
    assert r["intent"] == "aacsb_summary" and r["skill"] == "SQL" and "Assurance of learning" in r["answer"]
    r = _ask(client, fac, "Where is R practiced?")
    assert r["intent"] == "where_taught" and "BUAN 6356" in r["answer"]
    r = _ask(client, fac, "What's the weather like?")
    assert r["intent"] == "help" and r["citations"] == [] and "Why did" in r["answer"]
    # no records → refuses to guess
    r = _ask(client, fac, "Why did ZZZZ 9999 drop?")
    assert r["citations"] == [] and "won't guess" in r["answer"]
    # permissions
    assert client.post("/api/ask", headers=tokens["student"], json={"question": "Why did BUAN 6356 drop?"}).status_code == 403
    assert client.post("/api/ask", headers=fac, json={"question": "x"}).status_code == 422


def test_ask_with_model_verifies_citations(client, tokens, monkeypatch):
    """When Claude writes the answer, citations to records that don't exist are removed."""
    from app.services import ai, ask

    def fake(system, prompt, schema, effort="medium", max_tokens=0):
        if schema is ask._Route:
            return ask._Route(intent="undecided_gaps")
        return ask._Answer(answer="SQL is the top gap [1]. Also invented [99].")

    monkeypatch.setattr(ai, "structured", fake)
    r = _ask(client, tokens["faculty"], "what should I look at first?")
    assert r["engine"] == "claude" and r["intent"] == "undecided_gaps"
    assert "[99]" not in r["answer"] and "[1]" in r["answer"] and [c["n"] for c in r["citations"]] == [1]
    assert any("unsupported citation" in s for s in r["steps"])
