"""QuizMaker : genere un quiz a partir d'un cours, le corrige et produit un rapport de revision."""
import io
import json
import os
import random
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

STATIC_DIR = Path(__file__).parent / "static"
MAX_CHARS = 40000
MAX_UPLOAD = 5 * 1024 * 1024  # 5 Mo
app = FastAPI(title="QuizMaker")


def get_client() -> OpenAI:
    """Client compatible OpenAI : Azure, GitHub Models... selon les variables d'environnement."""
    base_url, api_key = os.getenv("LLM_BASE_URL"), os.getenv("LLM_API_KEY")
    if not base_url or not api_key:
        raise HTTPException(500, "LLM_BASE_URL et LLM_API_KEY doivent etre configures.")
    return OpenAI(base_url=base_url, api_key=api_key)


def ask_llm(system: str, user: str) -> dict:
    try:
        res = get_client().chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-5-mini"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return json.loads(res.choices[0].message.content)
    except HTTPException:
        raise
    except Exception as exc:  # erreur reseau, quota, JSON invalide...
        raise HTTPException(502, f"Erreur du modele : {exc}") from exc


class QuizRequest(BaseModel):
    course_text: str = Field(min_length=100, max_length=MAX_CHARS)
    n_questions: int = Field(5, ge=3, le=10)


class ReportItem(BaseModel):
    question: str
    topic: str
    chosen: str
    correct: str
    is_correct: bool


class ReportRequest(BaseModel):
    items: list[ReportItem] = Field(min_length=1, max_length=10)


QUIZ_SYSTEM = (
    "Tu es un professeur qui cree des QCM de revision. Reponds UNIQUEMENT avec un objet JSON : "
    '{"title": str, "questions": [{"question": str, "choices": [4 chaines], '
    '"answer_index": int (0 a 3), "explanation": str, "topic": str (notion courte)}]}. '
    "Base-toi uniquement sur le cours fourni, varie la difficulte, une seule bonne reponse par question. "
    "N'utilise jamais de choix du type \"toutes les reponses\" ou \"aucune des reponses\". "
    "Redige dans la langue du cours."
)

REPORT_SYSTEM = (
    "Tu es un tuteur bienveillant. A partir des resultats d'un quiz, reponds UNIQUEMENT avec un objet JSON : "
    '{"summary": str (2-3 phrases), "weak_topics": [{"topic": str, "advice": str}], "strengths": [str]}. '
    "Ne liste dans weak_topics que les notions ratees, avec un conseil de revision concret. "
    "Redige dans la langue des questions."
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/quiz")
def create_quiz(req: QuizRequest):
    data = ask_llm(QUIZ_SYSTEM, f"Cree {req.n_questions} questions a partir de ce cours :\n\n{req.course_text}")
    try:
        for q in data["questions"]:
            assert len(q["choices"]) == 4 and 0 <= int(q["answer_index"]) <= 3
            # On melange nous-memes les choix : le modele met trop souvent la bonne reponse en premier.
            good = q["choices"][int(q["answer_index"])]
            random.shuffle(q["choices"])
            q["answer_index"] = q["choices"].index(good)
    except (KeyError, TypeError, ValueError, AssertionError) as exc:
        raise HTTPException(502, "Le modele a renvoye un quiz mal forme, reessaie.") from exc
    return data


@app.post("/api/report")
def create_report(req: ReportRequest):
    return ask_llm(REPORT_SYSTEM, json.dumps([i.model_dump() for i in req.items], ensure_ascii=False))


def extract_text(name: str, content: bytes) -> str:
    ext = Path(name).suffix.lower()
    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    if ext == ".docx":
        from docx import Document
        return "\n".join(par.text for par in Document(io.BytesIO(content)).paragraphs)
    raise HTTPException(400, "Format non pris en charge : utilise un fichier PDF, DOCX, TXT ou MD.")


@app.post("/api/extract")
def extract(file: UploadFile = File(...)):
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Fichier trop lourd (5 Mo maximum).")
    try:
        text = extract_text(file.filename or "", content).strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Impossible de lire ce fichier.") from exc
    if len(text) < 100:
        raise HTTPException(400, "Pas assez de texte trouve (PDF scanne ou fichier vide ?).")
    return {"text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")