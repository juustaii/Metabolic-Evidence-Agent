from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import csv
import io
from pypdf import PdfReader
from docx import Document

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
STORE_PATH = APP_DIR / "obesity_evidence_store.json"
HTML_PATH = APP_DIR / "obesity-evidence-agent.html"

app = FastAPI(title="Obesity Evidence Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SourceType = Literal["guideline", "article", "trial"]


def crypto_id() -> str:
    return f"id-{datetime.utcnow().timestamp()}-{Path().name}"


def today_iso() -> str:
    return date.today().isoformat()
def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    filename_lower = filename.lower()
    text = ""

    if filename_lower.endswith('.pdf'):
        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

    elif filename_lower.endswith('.docx'):
        doc = Document(io.BytesIO(file_bytes))
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"

    else:
        text = file_bytes.decode('utf-8', errors='ignore')

    return text.strip()
    
    DEFAULT_STATE: Dict[str, Any] = {
    "documents": [
        {
            "id": "guideline-2026-01",
            "title": "Obesity management guideline for adults",
            "type": "guideline",
            "date": "2026-01-15",
            "citation": "guideline-2026-01",
            "population": "Adults with obesity and cardiometabolic risk",
            "intervention": "Lifestyle therapy, pharmacotherapy, bariatric surgery",
            "keywords": ["obesity", "adults", "glp-1", "bariatric surgery", "bmi"],
            "text": "Recommends stepwise obesity treatment using intensive lifestyle intervention, anti-obesity pharmacotherapy for eligible patients, and bariatric surgery for selected individuals with severe obesity. GLP-1 receptor agonists may be considered for adults who meet clinical criteria. Evidence quality is highest when outcomes are supported by randomized trials and long-term follow-up.",
            "sourceUrl": "",
        },
        {
            "id": "article-2025-11-glp1",
            "title": "Journal article on GLP-1 therapy in obesity",
            "type": "article",
            "date": "2025-11-02",
            "citation": "article-2025-11-glp1",
            "population": "Adults with obesity and type 2 diabetes",
            "intervention": "GLP-1 therapy",
            "keywords": ["glp-1", "diabetes", "obesity", "weight loss", "outcomes"],
            "text": "This article reports clinically meaningful weight reduction, improved glycemic outcomes, and tolerability considerations in adults with obesity and diabetes. The article discusses adherence, adverse effects, and the importance of shared decision-making. The authors emphasize that results should be interpreted in the context of existing obesity guidelines.",
            "sourceUrl": "",
        },
        {
            "id": "trial-NCT-OBESITY-2041",
            "title": "Active clinical trial registry entry",
            "type": "trial",
            "date": "2026-04-20",
            "citation": "trial-NCT-OBESITY-2041",
            "population": "Adults with severe obesity",
            "intervention": "Next-generation incretin therapy",
            "keywords": ["trial", "obesity", "incretin", "phase 3", "recruiting"],
            "text": "Recruiting phase 3 trial evaluating a next-generation incretin therapy for adults with severe obesity. Eligibility focuses on BMI thresholds, safety criteria, and prior treatment history. Primary outcomes include weight loss, metabolic markers, and adverse event reporting.",
            "sourceUrl": "",
        },
        {
            "id": "article-2025-09-peds",
            "title": "Pediatric obesity review",
            "type": "article",
            "date": "2025-09-10",
            "citation": "article-2025-09-peds",
            "population": "Children and adolescents with obesity",
            "intervention": "Family-based behavioral treatment",
            "keywords": ["pediatric obesity", "children", "adolescents", "family-based", "behavioral treatment"],
            "text": "Summarizes pediatric obesity management emphasizing family-based behavioral treatment, nutrition counseling, physical activity, and careful consideration of medication use. The review highlights the need for age-appropriate assessment and ongoing monitoring.",
            "sourceUrl": "",
        },
    ],
    "settings": {
        "keywords": "obesity, glp-1, bariatric surgery, diabetes",
        "exclude": "animal study, editorial",
        "recency": "365",
        "maxResults": 5,
        "strictMode": True,
        "includeCitations": True,
        "shortSynthesis": True,
        "autoIndex": True,
        "requireExact": True,
        "sourceFilters": {"guideline": True, "article": True, "trial": True},
    },
    "crawlQueue": [
        {
            "id": "crawl-1",
            "title": "Incoming guideline update",
            "type": "guideline",
            "date": "2026-07-01",
            "citation": "crawler-guideline-update-1",
            "text": "New obesity guideline update with expanded coverage of medication use, follow-up cadence, and evidence-based thresholds for escalation of therapy.",
            "status": "queued",
        }
    ],
}


def load_state() -> Dict[str, Any]:
    if not STORE_PATH.exists():
        return copy.deepcopy(DEFAULT_STATE)
    try:
        data = json.loads(STORE_PATH.read_text())
        return {
            "documents": data.get("documents", copy.deepcopy(DEFAULT_STATE["documents"])),
            "settings": {
                **copy.deepcopy(DEFAULT_STATE["settings"]),
                **data.get("settings", {}),
                "sourceFilters": {
                    **copy.deepcopy(DEFAULT_STATE["settings"]["sourceFilters"]),
                    **data.get("settings", {}).get("sourceFilters", {}),
                },
            },
            "crawlQueue": data.get("crawlQueue", copy.deepcopy(DEFAULT_STATE["crawlQueue"])),
        }
    except Exception:
        return copy.deepcopy(DEFAULT_STATE)


def save_state(state: Dict[str, Any]) -> None:
    STORE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def normalize_text(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() or ch.isspace() or ch == "-" else " " for ch in text).split())


def tokenize(text: str) -> List[str]:
    return [token for token in normalize_text(text).split(" ") if token]


def parse_uploaded_documents(filename: str, file_bytes: bytes) -> List[Dict[str, Any]]:
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    now = today_iso()

    # Process PDF and Word documents directly from binary bytes
    if ext in ["pdf", "docx"]:
        text = extract_text_from_file(file_bytes, filename)
        title = filename.rsplit(".", 1)[0]
        return [{
            "id": crypto_id(),
            "title": title,
            "type": "article",
            "date": now,
            "citation": f"{ext.upper()} Document ({filename})",
            "population": "",
            "intervention": "",
            "keywords": [],
            "text": text,
            "sourceUrl": ""
        }]

    # Decode text for JSON/CSV formats
    content = file_bytes.decode("utf-8", errors="ignore")

    if ext == "json":
        parsed = json.loads(content)
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = parsed.get("documents") or [parsed]
        else:
            items = [parsed]
        if not isinstance(items, list):
            items = [items]
        docs: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            docs.append({
                "id": item.get("id") or crypto_id(),
                "title": item.get("title") or filename,
                "type": item.get("type") or "article",
                "date": item.get("date") or now,
                "citation": item.get("citation") or item.get("id") or crypto_id(),
                "population": item.get("population", ""),
                "intervention": item.get("intervention", ""),
                "keywords": item.get("keywords") if isinstance(item.get("keywords"), list) else [],
                "text": item.get("text") or item.get("abstract") or json.dumps(item),
                "sourceUrl": item.get("sourceUrl", "")
            })
        return docs

    if ext == "csv":
        reader = csv.DictReader(io.StringIO(content))
        docs = []
        for row in reader:
            docs.append({
                "id": row.get("id") or f"upload-{datetime.utcnow().timestamp()}",
                "title": row.get("title") or row.get("name") or filename,
                "type": row.get("type") or "article",
                "date": row.get("date") or now,
                "citation": row.get("citation") or row.get("id") or f"upload-{datetime.utcnow().timestamp()}",
                "population": row.get("population", ""),
                "intervention": row.get("intervention", ""),
                "keywords": tokenize(row.get("keywords", "")),
                "text": row.get("text") or row.get("abstract") or json.dumps(row),
                "sourceUrl": row.get("sourceUrl", ""),
            })
        return docs

    # Fallback for standard PDF/DOCX or plain text files
    text = extract_text_from_file(file_bytes, filename)
    title = Path(filename).stem or filename

    return [{
        "id": crypto_id(),
        "title": title,
        "type": "article",
        "date": now,
        "citation": f"Uploaded File ({filename})",
        "population": "",
        "intervention": "",
        "keywords": tokenize(title + " " + text),
        "text": text,
        "sourceUrl": ""
    }]


def get_enabled_sources(settings: Dict[str, Any], selected_sources: Optional[List[str]] = None) -> List[str]:
    if selected_sources:
        return selected_sources
    filters = settings.get("sourceFilters") or {}
    enabled = [name for name, value in filters.items() if value]
    return enabled or ["guideline", "article", "trial"]


def recency_score(doc_date: str, window_days: Any) -> float:
    if not doc_date:
        return 0.0
    try:
        parsed = datetime.fromisoformat(doc_date)
    except ValueError:
        return 0.0
    age_days = (datetime.utcnow() - parsed).days
    if window_days == "all":
        return max(0.0, 30 - min(30, age_days / 30))
    try:
        limit = int(window_days or 365)
    except Exception:
        limit = 365
    if age_days > limit:
        return -12.0
    remaining = limit - age_days
    return max(0.0, round((remaining / limit) * 20, 2))


def rank_document(doc: Dict[str, Any], query: str, settings: Dict[str, Any], selected_sources: Optional[List[str]] = None):
    if doc.get("type") not in get_enabled_sources(settings, selected_sources):
        return None

    doc_text = normalize_text(" ".join([
        doc.get("title", ""),
        doc.get("citation", ""),
        doc.get("population", ""),
        doc.get("intervention", ""),
        " ".join(doc.get("keywords", [])),
        doc.get("text", ""),
    ]))

    excluded = tokenize(settings.get("exclude", ""))
    for term in excluded:
        if term and term in doc_text:
            return None

    query_tokens = tokenize(query)
    all_keywords = tokenize(f"{settings.get('keywords', '')} {' '.join(doc.get('keywords', []))}")
    recency_weight = recency_score(doc.get("date", ""), settings.get("recency"))
    exact_title = sum(1 for token in query_tokens if token in doc.get("title", "").lower())
    title_hits = sum(1 for token in query_tokens if token in tokenize(doc.get("title", "")))
    body_hits = sum(1 for token in query_tokens if token in doc_text)
    keyword_hits = sum(1 for token in query_tokens if token in all_keywords)
    settings_hits = sum(1 for token in tokenize(settings.get("keywords", "")) if token in doc_text)

    score = (body_hits * 10) + (title_hits * 14) + (keyword_hits * 6) + (settings_hits * 3) + recency_weight
    if settings.get("requireExact") and exact_title > 0:
        score += 12
    if doc.get("type") == "guideline":
        score += 10
    if doc.get("type") == "article":
        score += 4
    if doc.get("type") == "trial":
        score += 2
    if not query_tokens:
        score = recency_weight + 5
    if query.lower() in doc.get("title", "").lower():
        score += 20

    snippet = extract_snippet(doc.get("text", ""), query)
    reasons = []
    if title_hits:
        reasons.append("title match")
    if keyword_hits:
        reasons.append("keyword match")
    if doc.get("type") == "guideline" and "guideline" not in reasons:
        reasons.append("guideline priority")
    if recency_weight > 0:
        reasons.append("recent")

    return {
        **doc,
        "score": score,
        "snippets": [snippet],
        "relevance_reason": reasons or ["repository match"],
    }


def extract_snippet(text: str, query: str) -> str:
    sentences = []
    current = []
    for chunk in text.replace("\n", " ").split("."):
        chunk = chunk.strip()
        if chunk:
            sentences.append(chunk + ".")
    if not sentences:
        return text[:240]
    q_tokens = tokenize(query)
    ranked = []
    for idx, sentence in enumerate(sentences):
        lower = normalize_text(sentence)
        score = sum(1 for token in q_tokens if token in lower)
        score += max(0, 3 - idx * 0.3)
        if score > 0:
            ranked.append((score, sentence))
    if ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1].strip()
    return sentences[0].strip()


def build_answer(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "not found in the repository"
    best = results[0]
    snippets = " ".join(result["snippets"][0] for result in results[:3] if result.get("snippets"))
    return f"The strongest match is {best['title']}. {snippets}".strip()


class FilterModel(BaseModel):
    source_types: Optional[List[SourceType]] = None
    keywords: Optional[List[str]] = None
    excluded_terms: Optional[List[str]] = None
    recency_days: Optional[int] = Field(default=365)
    max_results: Optional[int] = Field(default=5)


class QueryRequest(BaseModel):
    question: str
    filters: Optional[FilterModel] = None


class DocumentModel(BaseModel):
    id: Optional[str] = None
    title: str
    type: SourceType
    date: Optional[str] = None
    citation: Optional[str] = None
    population: Optional[str] = ""
    intervention: Optional[str] = ""
    keywords: Optional[List[str]] = None
    text: str
    sourceUrl: Optional[str] = ""


class SettingsModel(BaseModel):
    keywords: Optional[str] = None
    exclude: Optional[str] = None
    recency: Optional[str] = None
    maxResults: Optional[int] = None
    strictMode: Optional[bool] = None
    includeCitations: Optional[bool] = None
    shortSynthesis: Optional[bool] = None
    autoIndex: Optional[bool] = None
    requireExact: Optional[bool] = None
    sourceFilters: Optional[Dict[str, bool]] = None


class CrawlerItemModel(BaseModel):
    id: Optional[str] = None
    title: str
    type: SourceType
    date: Optional[str] = None
    citation: Optional[str] = None
    text: str
    status: Optional[str] = "queued"


class StateModel(BaseModel):
    documents: List[DocumentModel]
    settings: Dict[str, Any]
    crawlQueue: List[Dict[str, Any]]


@app.get("/")
def index():
    if HTML_PATH.exists():
        return FileResponse(HTML_PATH)
    raise HTTPException(status_code=404, detail="HTML file not found")


@app.get("/obesity-evidence-agent.html")
def index_alias():
    return index()


@app.get("/api/obesity-evidence/health")
def health():
    return {"ok": True, "service": "obesity-evidence-api"}


@app.get("/api/obesity-evidence/contract")
def contract():
    return {
        "api_version": "v1",
        "base_url": "/api/obesity-evidence",
        "response_policy": {
            "mode": "strict_retrieval",
            "answer_only_from_approved_sources": True,
            "citations_required": True,
            "fallback_message": "not found in the repository",
            "no_external_reasoning": True,
        },
        "endpoints": [
            {"method": "GET", "path": "/state"},
            {"method": "PUT", "path": "/state"},
            {"method": "POST", "path": "/query"},
            {"method": "GET", "path": "/documents"},
            {"method": "POST", "path": "/documents"},
            {"method": "POST", "path": "/upload"},
            {"method": "PUT", "path": "/settings"},
            {"method": "POST", "path": "/crawler/queue"},
            {"method": "POST", "path": "/crawler/process"},
            {"method": "GET", "path": "/export"},
        ],
    }


@app.get("/api/obesity-evidence/state")
def get_state():
    return load_state()


@app.put("/api/obesity-evidence/state")
def put_state(payload: StateModel):
    state = {
        "documents": [doc.model_dump() for doc in payload.documents],
        "settings": payload.settings,
        "crawlQueue": payload.crawlQueue,
    }
    save_state(state)
    return state


@app.get("/api/obesity-evidence/export")
def export_state():
    return load_state()


@app.get("/api/obesity-evidence/documents")
def list_documents():
    return load_state()["documents"]


@app.post("/api/obesity-evidence/documents")
def add_document(doc: DocumentModel):
    state = load_state()
    record = doc.model_dump()
    record["id"] = record.get("id") or f"doc-{datetime.utcnow().timestamp()}"
    record["date"] = record.get("date") or today_iso()
    record["citation"] = record.get("citation") or record["id"]
    record["keywords"] = record.get("keywords") or tokenize(f"{record['title']} {record['text']}")
    state["documents"] = [d for d in state["documents"] if d.get("citation") != record["citation"]]
    state["documents"].insert(0, record)
    save_state(state)
    return record


@app.post("/api/obesity-evidence/upload")
async def upload_file(file: UploadFile = File(...)):
    state = load_state()
    file_bytes = await file.read()
    
    filename = file.filename or "upload.txt"
    docs = parse_uploaded_documents(filename, file_bytes)
    
    added = []
    for doc in docs:
        doc["keywords"] = doc.get("keywords") or tokenize(f"{doc.get('title', '')} {doc.get('text', '')}")
        state["documents"] = [d for d in state["documents"] if d.get("citation") != doc["citation"]]
        state["documents"].insert(0, doc)
        added.append(doc)
    
    save_state(state)
    
    upload_dir = APP_DIR / "uploads"
    upload_dir.mkdir(exist_ok=True)
    safe_name = Path(filename).name
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{safe_name}"
    (upload_dir / stored_name).write_bytes(file_bytes)
    
    return {"status": "ok", "added": added}
    save_state(state)
    return {
        "filename": file.filename,
        "stored_as": stored_name,
        "added": added,
        "count": len(added),
        "state": state,
    }


@app.put("/api/obesity-evidence/settings")
def update_settings(settings: SettingsModel):
    state = load_state()
    current = state["settings"]
    updates = settings.model_dump(exclude_none=True)
    if "sourceFilters" in updates and updates["sourceFilters"] is not None:
        current["sourceFilters"] = {**current.get("sourceFilters", {}), **updates.pop("sourceFilters")}
    current.update(updates)
    state["settings"] = current
    save_state(state)
    return current


@app.post("/api/obesity-evidence/crawler/queue")
def queue_crawler_item(item: CrawlerItemModel):
    state = load_state()
    record = item.model_dump()
    record["id"] = record.get("id") or f"crawl-{datetime.utcnow().timestamp()}"
    record["date"] = record.get("date") or today_iso()
    record["status"] = record.get("status") or "queued"
    state["crawlQueue"].insert(0, record)
    save_state(state)
    return record


@app.post("/api/obesity-evidence/crawler/process")
def process_crawler_queue():
    state = load_state()
    queued = [item for item in state["crawlQueue"] if item.get("status") == "queued"]
    added = []
    for item in queued:
        document = {
            "id": item.get("id") or f"doc-{datetime.utcnow().timestamp()}",
            "title": item.get("title", "Untitled crawler item"),
            "type": item.get("type", "article"),
            "date": item.get("date") or today_iso(),
            "citation": item.get("citation") or item.get("id") or f"crawl-{datetime.utcnow().timestamp()}",
            "population": item.get("population", ""),
            "intervention": item.get("intervention", ""),
            "keywords": tokenize(f"{item.get('title', '')} {item.get('text', '')}"),
            "text": item.get("text", ""),
            "sourceUrl": item.get("sourceUrl", ""),
        }
        state["documents"] = [d for d in state["documents"] if d.get("citation") != document["citation"]]
        state["documents"].insert(0, document)
        added.append(document)
    state["crawlQueue"] = [
        {**item, "status": "processed"} if item.get("status") == "queued" else item
        for item in state["crawlQueue"]
    ]
    save_state(state)
    return {"processed": len(queued), "added": added, "state": state}


@app.post("/api/obesity-evidence/query")
def query_documents(payload: QueryRequest):
    state = load_state()
    settings = copy.deepcopy(state["settings"])
    filters = payload.filters or FilterModel()
    if filters.recency_days is not None:
        settings["recency"] = str(filters.recency_days)
    if filters.keywords:
        settings["keywords"] = ", ".join(filters.keywords)
    if filters.excluded_terms:
        settings["exclude"] = ", ".join(filters.excluded_terms)
    selected_sources = filters.source_types or get_enabled_sources(settings)
    max_results = filters.max_results or settings.get("maxResults", 5)
    ranked = [
        rank_document(doc, payload.question, settings, selected_sources)
        for doc in state["documents"]
    ]
    ranked = [doc for doc in ranked if doc is not None]

    if filters.keywords:
        keyword_tokens = [token.lower() for token in filters.keywords]
        ranked = [
            doc for doc in ranked
            if any(token in normalize_text(" ".join([doc.get("title", ""), doc.get("text", ""), " ".join(doc.get("keywords", []))])) for token in keyword_tokens)
        ]

    if filters.excluded_terms:
        excluded_tokens = [token.lower() for token in filters.excluded_terms]
        ranked = [
            doc for doc in ranked
            if not any(token in normalize_text(" ".join([doc.get("title", ""), doc.get("text", ""), " ".join(doc.get("keywords", []))])) for token in excluded_tokens)
        ]

    ranked.sort(key=lambda doc: doc.get("score", 0), reverse=True)
    ranked = ranked[:max_results]

    if ranked:
        answer = build_answer(ranked)
    else:
        answer = "not found in the repository"

    return {
        "question": payload.question,
        "mode": "strict_retrieval",
        "results": ranked,
        "answer": answer,
        "fallback": "not found in the repository",
    }


@app.get("/api/obesity-evidence/openapi-contract")
def openapi_contract():
    return contract()
