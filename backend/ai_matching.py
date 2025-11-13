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
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# -----------------------------
# PROMPTS (unchanged, using your original templates)
# -----------------------------
skills_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score a candidate's technical skills against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```
...
Respond ONLY with this JSON:
{{"skills_score": 8, "explanation": "Strengths: Python and SQL present. Gaps: Missing AWS."}}
""")
# (Repeat the same prompts content for experience_prompt, education_prompt, projects_prompt)
experience_prompt = PromptTemplate.from_template("""...""")
education_prompt = PromptTemplate.from_template("""...""")
projects_prompt = PromptTemplate.from_template("""...""")

# -----------------------------
# State
# -----------------------------
class MatchingState(TypedDict):
    jd_text: str
    cv_text: str
    results: dict
    final_output: dict

# -----------------------------
# Helpers: extract JSON from mixed text
# -----------------------------
def extract_json_object_from_text(text: str):
    """Return a Python object if JSON found inside text; else None."""
    if not text or not text.strip():
        return None
    # direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # find {...} patterns
    candidates = re.findall(r'\{.*\}', text, flags=re.DOTALL)
    candidates = sorted(candidates, key=len, reverse=True)
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            continue
    # try substrings starting at '{'
    for i, ch in enumerate(text):
        if ch == '{':
            try:
                return json.loads(text[i:])
            except Exception:
                continue
    return None

# -----------------------------
# GEMINI CALLER (robust)
# -----------------------------
def call_gemini_api(prompt_text: str, category: str = "generic") -> str:
    """
    Call Gemini API with timeout and defensive handling. Always return a string.
    If internal error or mock mode, return a JSON string (so json.loads() won't fail).
    """
    if USE_MOCK_GEMINI or not GEMINI_API_KEY:
        print(f"[ai_matching] Using mock response for '{category}' (USE_MOCK_GEMINI={USE_MOCK_GEMINI})")
        mock = {
            "skills": {"skills_score": 8, "explanation": "Mock: Python and SQL found."},
            "experience": {"experience_score": 6, "explanation": "Mock: 3 years vs required 5."},
            "education": {"education_score": 9, "explanation": "Mock: B.Tech in CS."},
            "projects": {"projects_score": 7, "explanation": "Mock: Relevant project."},
            "generic": {"score": 0, "explanation": "Mock default"}
        }
        return json.dumps(mock.get(category, mock["generic"]))

    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}

    for attempt in range(2):
        try:
            response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=15)
            print(f"[ai_matching] Gemini status {response.status_code} (attempt {attempt+1}) for '{category}'")
            if response.status_code != 200:
                print("[ai_matching] Gemini non-200:", response.status_code, response.text[:800])
                return json.dumps({"score": 0, "explanation": f"Gemini non-200:{response.status_code}"})
            try:
                resp_json = response.json()
            except Exception as e:
                print("[ai_matching] .json() decode failed:", e)
                print("Raw response (truncated):", response.text[:2000])
                return json.dumps({"score": 0, "explanation": "Gemini returned non-JSON body"})
            try:
                content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                if not content or not content.strip():
                    return json.dumps({"score": 0, "explanation": "Empty content from Gemini"})
                content = content.strip().lstrip("```json").rstrip("```").strip()
                return content
            except Exception as e:
                print("[ai_matching] Unexpected Gemini JSON shape:", e)
                print("Raw JSON (truncated):", json.dumps(resp_json)[:2000])
                return json.dumps({"score": 0, "explanation": "Unexpected Gemini response format"})
        except requests.Timeout:
            print(f"[ai_matching] Gemini timeout (attempt {attempt+1})")
            if attempt == 1:
                return json.dumps({"score": 0, "explanation": "Gemini timeout"})
            time.sleep(1)
        except requests.RequestException as e:
            print("[ai_matching] Gemini request exception:", e)
            if attempt == 1:
                return json.dumps({"score": 0, "explanation": f"Gemini request exception: {str(e)[:200]}"})
            time.sleep(1)

    return json.dumps({"score": 0, "explanation": "Gemini call failed"})

# -----------------------------
# Node functions (defensive)
# -----------------------------
def skills_node(state: MatchingState):
    print("--- Running Skills Node ---")
    prompt_text = skills_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="skills")
    parsed = extract_json_object_from_text(response_str)
    if parsed is None:
        try:
            parsed = json.loads(response_str)
        except Exception as e:
            print("[ai_matching] Failed to parse skills response:", e)
            print("Raw (truncated):", (response_str or "")[:2000])
            parsed = {"skills_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}
    if isinstance(parsed, dict):
        parsed.setdefault("skills_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"skills_score": 0, "explanation": "Unexpected response type from Gemini."}
    results = state.get("results", {}) or {}
    results["skills"] = parsed
    state["results"] = results
    return {"results": results}

def experience_node(state: MatchingState):
    print("--- Running Experience Node ---")
    prompt_text = experience_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="experience")
    parsed = extract_json_object_from_text(response_str)
    if parsed is None:
        try:
            parsed = json.loads(response_str)
        except Exception as e:
            print("[ai_matching] Failed to parse experience response:", e)
            print("Raw (truncated):", (response_str or "")[:2000])
            parsed = {"experience_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}
    if isinstance(parsed, dict):
        parsed.setdefault("experience_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"experience_score": 0, "explanation": "Unexpected response type from Gemini."}
    results = state.get("results", {}) or {}
    results["experience"] = parsed
    state["results"] = results
    return {"results": results}

def education_node(state: MatchingState):
    print("--- Running Education Node ---")
    prompt_text = education_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="education")
    parsed = extract_json_object_from_text(response_str)
    if parsed is None:
        try:
            parsed = json.loads(response_str)
        except Exception as e:
            print("[ai_matching] Failed to parse education response:", e)
            print("Raw (truncated):", (response_str or "")[:2000])
            parsed = {"education_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}
    if isinstance(parsed, dict):
        parsed.setdefault("education_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"education_score": 0, "explanation": "Unexpected response type from Gemini."}
    results = state.get("results", {}) or {}
    results["education"] = parsed
    state["results"] = results
    return {"results": results}

def projects_node(state: MatchingState):
    print("--- Running Projects Node ---")
    prompt_text = projects_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="projects")
    parsed = extract_json_object_from_text(response_str)
    if parsed is None:
        try:
            parsed = json.loads(response_str)
        except Exception as e:
            print("[ai_matching] Failed to parse projects response:", e)
            print("Raw (truncated):", (response_str or "")[:2000])
            parsed = {"projects_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}
    if isinstance(parsed, dict):
        parsed.setdefault("projects_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"projects_score": 0, "explanation": "Unexpected response type from Gemini."}
    results = state.get("results", {}) or {}
    results["projects"] = parsed
    state["results"] = results
    return {"results": results}

def aggregate_node(state: MatchingState):
    print("--- Running Aggregate Node ---")
    results = state.get("results", {}) or {}
    def safe_score(obj, key, fallback=0):
        try:
            val = obj.get(key, fallback)
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
            if isinstance(val, str) and str(val).replace('.', '', 1).isdigit():
                return float(val)
            return fallback
        except Exception:
            return fallback
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
            "projects": {"score": scores["projects"], "explanation": results.get("projects", {}).get("explanation", "") or ""}
        }
    }
    return {"final_output": final_output}

# -----------------------------
# Graph setup
# -----------------------------
def setup_graph():
    workflow = StateGraph(MatchingState)
    workflow.add_node("skills", skills_node)
    workflow.add_node("experience", experience_node)
    workflow.add_node("education", education_node)
    workflow.add_node("projects", projects_node)
    workflow.add_node("aggregate", aggregate_node)
    workflow.set_entry_point("skills")
    workflow.add_edge("skills", "experience")
    workflow.add_edge("experience", "education")
    workflow.add_edge("education", "projects")
    workflow.add_edge("projects", "aggregate")
    workflow.add_edge("aggregate", END)
    return workflow.compile()
