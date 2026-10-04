from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)
COURSE = "x" * 200


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_quiz_rejects_short_course():
    r = client.post("/api/quiz", json={"course_text": "trop court", "n_questions": 5})
    assert r.status_code == 422


def test_quiz_shuffles_but_keeps_correct_answer(monkeypatch):
    fake = {"title": "T", "questions": [
        {"question": "Q?", "choices": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "e", "topic": "t"}]}
    monkeypatch.setattr(main, "ask_llm", lambda system, user: fake)
    r = client.post("/api/quiz", json={"course_text": COURSE, "n_questions": 3})
    assert r.status_code == 200
    q = r.json()["questions"][0]
    assert sorted(q["choices"]) == ["A", "B", "C", "D"]
    assert q["choices"][q["answer_index"]] == "A"  # la bonne reponse suit le melange


def test_quiz_malformed_llm_answer_returns_502(monkeypatch):
    bad = {"title": "T", "questions": [{"question": "Q?", "choices": ["A", "B"], "answer_index": 0}]}
    monkeypatch.setattr(main, "ask_llm", lambda system, user: bad)
    r = client.post("/api/quiz", json={"course_text": COURSE, "n_questions": 3})
    assert r.status_code == 502


def test_extract_text_file():
    r = client.post("/api/extract", files={"file": ("cours.txt", b"a" * 200, "text/plain")})
    assert r.status_code == 200
    assert len(r.json()["text"]) == 200


def test_extract_rejects_unsupported_format():
    r = client.post("/api/extract", files={"file": ("virus.exe", b"a" * 200, "application/octet-stream")})
    assert r.status_code == 400
