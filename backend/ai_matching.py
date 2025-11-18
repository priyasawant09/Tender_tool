# backend/ai_matching.py
import os
import json
import requests
import time
import re
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from typing import TypedDict

# -----------------------------
# Config / API Setup
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USE_MOCK_GEMINI = os.getenv("USE_MOCK_GEMINI", "false").lower() in ("1", "true", "yes")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# -----------------------------
# Combined Prompt (one call per CV)
# -----------------------------
combined_prompt = PromptTemplate.from_template("""
You are an objective, precise recruitment scoring assistant. Your job is to read a JOB DESCRIPTION and a CANDIDATE CV (or concise summary) and return a single, machine-parseable JSON object that scores the candidate on four dimensions: skills, experience, education, and projects.

INPUTS
Job Description:
```{jd_text}```

Candidate CV (or concise summary):
```{cv_text}```

OUTPUT FORMAT (required)
Return EXACTLY one valid JSON object and nothing else. No explanation, no markdown, no code fences, no additional fields. The JSON must include the following keys:

{
  "skills": {"score": int (1-10), "explanation": string, "evidence": [string, ...]},
  "experience": {"score": int (1-10), "explanation": string, "years": number or null},
  "education": {"score": int (1-10), "explanation": string, "degree": string or null},
  "projects": {"score": int (1-10), "explanation": string, "top_project": string or null}
}

SCORING RULES (strict)
- All scores must be integers between 1 and 10 inclusive.
- Use 9–10 only when the CV strongly and directly meets or exceeds the JD requirements.
- Use 7–8 for a good match with minor gaps; 4–6 for partial match; 1–3 for poor or no match.
- If a value is unknown/unavailable, use `null` for that field (not an empty string), but still provide an explanation and set score appropriately.

WHAT TO INCLUDE IN EACH FIELD
- skills.explanation — 1–2 concise sentences summarizing why the score was chosen.
- skills.evidence — an array (2–4 short strings) quoting exact phrases or short fragments from the CV that justify the score. If no direct phrases, provide the most relevant paraphrase.
- experience.years — numeric total years of relevant experience if you can infer it, else null.
- experience.explanation — 1–2 sentences comparing years & roles to the JD requirements.
- education.degree — short string (e.g., "B.Tech Computer Science") if present in CV, else null.
- education.explanation — 1 sentence that explains match/mismatch to JD degree requirement.
- projects.top_project — name/title/short description of the most relevant project in CV, else null.
- projects.explanation — 1–2 sentences describing how the top project demonstrates relevant skills.

GUIDELINES FOR EVIDENCE EXTRACTION
- Prefer direct text from the CV: exact phrases or job titles, e.g., "Senior Data Engineer", "3 years", "AWS, Python".
- If quoting, keep quotes short (<= 10 words) and exact.
- If you infer (e.g., calculating years), explain the inference in explanation and set `years` accordingly.

PRIORITIZATION
- If the JD lists specific *required* skills, those should be weighted heavily when scoring skills.
- If JD uses vague words like "experience with cloud", treat them as lower-precision requirements — call out the ambiguity in the explanation.

ROBUSTNESS RULES
- If you cannot produce valid JSON, return exactly: {"error":"no_json_found"}
- Do not include any additional keys in the top-level JSON.
- Keep explanations concise (max 25 words each).
- Ensure all numeric scores are integers (round or floor floats to nearest integer).
- Ensure arrays (evidence) contain at least one string when evidence exists, otherwise an empty array [].

EXAMPLE (valid output)
{
  "skills": {"score":8, "explanation":"Strong Python and SQL evidence; missing cloud infra.", "evidence":["Python (5+ yrs)","SQL, Postgres"]},
  "experience": {"score":7, "explanation":"5 years in relevant roles, slightly junior to Senior requirement.", "years":5},
  "education": {"score":9, "explanation":"B.Tech in Computer Science matches requirement.", "degree":"B.Tech Computer Science"},
  "projects": {"score":7, "explanation":"Relevant ETL project demonstrating data pipeline skills.", "top_project":"ETL pipeline for payments reconciliation"}
}

IMPORTANT: Output must be parsable by a machine. Produce exactly the JSON structure above and nothing else.
""")


# -----------------------------
# State
# -----------------------------
class MatchingState(TypedDict):
    jd_text: str
    cv_text: str
    cv_summary: str
    results: dict
    final_output: dict

# -----------------------------
# Utilities: JSON extraction & truncation
# -----------------------------
def extract_json_object_from_text(text: str):
    """
    Find a balanced { ... } JSON object in noisy text and return the parsed object if found.
    Returns None if no valid JSON object can be extracted.
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    # strip common code fences
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)

    # quick direct parse
    try:
        return json.loads(s)
    except Exception:
        pass

    # find candidates by scanning for '{' and matching braces
    starts = [i for i, ch in enumerate(s) if ch == '{']
    best = None
    for start in starts:
        stack = 0
        for i in range(start, len(s)):
            if s[i] == '{':
                stack += 1
            elif s[i] == '}':
                stack -= 1
                if stack == 0:
                    cand = s[start:i+1]
                    try:
                        parsed = json.loads(cand)
                        # prefer larger candidate (more likely complete)
                        if not best or len(cand) > len(best[0]):
                            best = (cand, parsed)
                    except Exception:
                        pass
                    break
    return best[1] if best else None

def summarize_text_simple(text, head_chars=3000, tail_chars=800):
    """Keep the beginning and the end of the CV to preserve both overview and recent details."""
    if not text:
        return ""
    if len(text) <= head_chars + tail_chars:
        return text
    return text[:head_chars] + "\n\n...[truncated]...\n\n" + text[-tail_chars:]

# -----------------------------
# Robust Gemini Caller (with retries/backoff + RetryInfo handling)
# -----------------------------
def call_gemini_api(prompt_text: str, category: str = "generic", max_retries: int = 4, timeout=(5,25)) -> str:
    """
    Calls Gemini API and returns raw model text. On failure returns a JSON string describing the error.
    Implements retries on 429 with backoff using RetryInfo if present.
    """
    # Mock fallback
    if USE_MOCK_GEMINI or not GEMINI_API_KEY:
        mock = {
            "skills": json.dumps({"skills_score": 8, "explanation": "Mock: Python and SQL found."}),
            "experience": json.dumps({"experience_score": 6, "explanation": "Mock: 3 years vs required 5."}),
            "education": json.dumps({"education_score": 9, "explanation": "Mock: B.Tech in CS."}),
            "projects": json.dumps({"projects_score": 7, "explanation": "Mock: Relevant project."}),
            "generic": json.dumps({"score": 0, "explanation": "Mock default"})
        }
        return mock.get(category, mock["generic"])

    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    headers = {"Content-Type": "application/json"}

    attempt = 0
    while attempt <= max_retries:
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
        except requests.Timeout as e:
            print(f"[ai_matching] Gemini timeout for '{category}' attempt {attempt}: {e}")
            wait_s = (2 ** attempt) + 0.1
            time.sleep(wait_s)
            attempt += 1
            continue
        except requests.RequestException as e:
            print(f"[ai_matching] Gemini request exception for '{category}' attempt {attempt}: {e}")
            wait_s = (2 ** attempt) + 0.1
            time.sleep(wait_s)
            attempt += 1
            continue

        if resp.status_code == 200:
            try:
                resp_json = resp.json()
                text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            except Exception as e:
                print("[ai_matching] Failed to parse Gemini success JSON:", e)
                return json.dumps({"score": 0, "explanation": "Gemini returned unexpected structure", "raw": resp.text[:1000]})

        # Non-200 handling
        body = resp.text
        print(f"[ai_matching] Gemini non-200 ({resp.status_code}) Body (truncated): {body[:1000]}")

        if resp.status_code == 429:
            # Try to get retry delay from JSON details (RetryInfo) or Retry-After header
            retry_seconds = None
            try:
                j = resp.json()
                if "error" in j and "details" in j["error"]:
                    for d in j["error"]["details"]:
                        if d.get("@type", "").endswith("RetryInfo"):
                            rd = d.get("retryDelay")
                            if rd:
                                s = str(rd)
                                if s.endswith("s"):
                                    retry_seconds = float(s[:-1])
                                else:
                                    retry_seconds = float(s)
                                break
            except Exception:
                pass

            if retry_seconds is None:
                ra = resp.headers.get("Retry-After")
                try:
                    if ra:
                        retry_seconds = float(ra)
                except Exception:
                    retry_seconds = None

            if retry_seconds is None:
                retry_seconds = (2 ** attempt) + 0.2

            print(f"[ai_matching] 429 received, retrying in {retry_seconds:.2f}s (attempt {attempt}/{max_retries})")
            time.sleep(retry_seconds)
            attempt += 1
            continue
        else:
            # Other 4xx/5xx: do not retry indefinitely
            return json.dumps({"score": 0, "explanation": f"Gemini non-200:{resp.status_code}", "raw": body[:1000]})

    # Exhausted retries
    return json.dumps({"score": 0, "explanation": "API Error: retries exhausted / quota exceeded"})

# -----------------------------
# Summarization node
# -----------------------------
def summarize_cv_node(state: MatchingState):
    print("--- Running Summarization Node ---")
    cv_text = state.get("cv_text", "") or ""
    # Keep summarization prompt bounded to avoid huge model input
    cv_text_for_summary = cv_text[:25000]
    summary_template = """
You are an expert HR assistant. Summarize the CV into a compact structured summary (max 3000 characters).

Extract ONLY:
- Skills (comma separated)
- Total years of experience and key roles
- Education (degrees)
- Major relevant projects
- Industry-specific experience (if present)

Return plain text summary only, no JSON. Keep it concise.

CV:
{cv_text}
"""
    prompt = summary_template.format(cv_text=cv_text_for_summary)
    resp = call_gemini_api(prompt, category="summary")
    # If the model returned JSON or long text, fallback to plain text extraction
    try:
        parsed = json.loads(resp)
        if isinstance(parsed, dict):
            parts = []
            for k, v in parsed.items():
                parts.append(f"{k}: {v}")
            summary_text = " | ".join(parts)[:4000]
        else:
            summary_text = str(parsed)[:4000]
    except Exception:
        summary_text = str(resp)[:4000]

    return {"cv_summary": summary_text}

# -----------------------------
# Combined scoring node (single call per CV)
# -----------------------------
def combined_scoring_node(state: MatchingState):
    print("--- Running Combined Scoring Node ---")
    jd_text = (state.get("jd_text") or "")[:2000]
    # Prefer the pre-computed summary if present (smaller prompt)
    cv_text = state.get("cv_summary") or state.get("cv_text") or ""
    # Truncate for prompt size
    cv_short = summarize_text_simple(cv_text, head_chars=3000, tail_chars=800)

    prompt_text = combined_prompt.format(jd_text=jd_text, cv_text=cv_short)

    # One call per CV
    response_str = call_gemini_api(prompt_text, category="combined")

    # Try to extract valid JSON
    parsed = None
    try:
        parsed = json.loads(response_str)
    except Exception:
        parsed = extract_json_object_from_text(response_str)

    if not parsed or not isinstance(parsed, dict):
        # fallback safe structure
        return {"results": {
            "skills": {"skills_score": 0, "explanation": "Invalid or missing JSON from model."},
            "experience": {"experience_score": 0, "explanation": "Invalid or missing JSON from model."},
            "education": {"education_score": 0, "explanation": "Invalid or missing JSON from model."},
            "projects": {"projects_score": 0, "explanation": "Invalid or missing JSON from model."},
        }}

    # Normalize parsed structure: accept either { "skills": {"score":..}} or {"skills_score":..}
    def normalize_section(sec_name, parsed_obj):
        sec = parsed_obj.get(sec_name, {}) or {}
        # if top-level had "skills_score" style
        score_key_alt = f"{sec_name}_score"
        if isinstance(parsed_obj.get(score_key_alt), (int, float, str)):
            score_val = parsed_obj.get(score_key_alt)
            explanation_val = parsed_obj.get("explanation", "") or ""
            return {f"{sec_name}_score": float(score_val), "explanation": explanation_val}
        # if sec is a dict with keys 'score' and 'explanation'
        if isinstance(sec, dict):
            s = sec.get("score", sec.get(f"{sec_name}_score", 0))
            e = sec.get("explanation", "")
            return {f"{sec_name}_score": float(s) if isinstance(s, (int, float, str)) and str(s).replace('.', '', 1).isdigit() else 0, "explanation": e}
        # fallback
        return {f"{sec_name}_score": 0, "explanation": ""}

    skills_parsed = normalize_section("skills", parsed)
    experience_parsed = normalize_section("experience", parsed)
    education_parsed = normalize_section("education", parsed)
    projects_parsed = normalize_section("projects", parsed)

    current_results = {
        "skills": skills_parsed,
        "experience": experience_parsed,
        "education": education_parsed,
        "projects": projects_parsed
    }

    return {"results": current_results}

# -----------------------------
# Aggregate node (unchanged)
# -----------------------------
def aggregate_node(state: MatchingState):
    print("--- Running Aggregate Node ---")
    results = state.get("results", {}) or {}

    def safe_score(obj, key, fallback=0):
        try:
            val = obj.get(key, fallback)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str) and val.replace('.', '', 1).isdigit():
                return float(val) if '.' in val else float(int(val))
            return float(fallback)
        except Exception:
            return float(fallback)

    scores = {
        "skills": safe_score(results.get("skills", {}), "skills_score", 0),
        "experience": safe_score(results.get("experience", {}), "experience_score", 0),
        "education": safe_score(results.get("education", {}), "education_score", 0),
        "projects": safe_score(results.get("projects", {}), "projects_score", 0),
    }

    weights = {"skills": 0.3, "experience": 0.4, "education": 0.1, "projects": 0.2}
    overall_score = round(sum(scores[k] * weights.get(k, 0) for k in scores), 1)

    final_output = {
        "overall_score": overall_score,
        "details": {
            "skills": {"score": scores["skills"], "explanation": results.get("skills", {}).get("explanation", "") or ""},
            "experience": {"score": scores["experience"], "explanation": results.get("experience", {}).get("explanation", "") or ""},
            "education": {"score": scores["education"], "explanation": results.get("education", {}).get("explanation", "") or ""},
            "projects": {"score": scores["projects"], "explanation": results.get("projects", {}).get("explanation", "") or ""},
        }
    }
    return {"final_output": final_output}

# -----------------------------
# Graph setup (summarize -> combined -> aggregate)
# -----------------------------
def setup_graph():
    workflow = StateGraph(MatchingState)
    workflow.add_node("summarize", summarize_cv_node)
    workflow.add_node("combined", combined_scoring_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("summarize")
    workflow.add_edge("summarize", "combined")
    workflow.add_edge("combined", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile()
