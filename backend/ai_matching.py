# ai_matching.py
import os
import json
import requests
import time
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from typing import TypedDict

# -----------------------------
# Config / API Setup
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Allow a quick local/dev override to use mock responses while debugging:
USE_MOCK_GEMINI = os.getenv("USE_MOCK_GEMINI", "false").lower() in ("1", "true", "yes")

API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# -----------------------------
# PROMPTS
# -----------------------------
skills_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score a candidate's technical skills against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1. From the Job Description, identify the 4–6 most critical technical skills, programming languages, and tools required.
2. Meticulously scan the CV to find direct evidence for each of the core requirements.
3. Based on the scoring rubric below, assign a score.
4. Write a concise explanation justifying your score, explicitly mentioning 2–3 key skills the candidate possesses and any critical skills that are missing.
5. The explanation should clearly list strengths and gaps using bullet points.

**Scoring Rubric:**
- **9–10 (Excellent Match):** Strong evidence for all core requirements.
- **7–8 (Good Match):** Meets most core requirements.
- **4–6 (Fair Match):** Meets some requirements but has gaps.
- **1–3 (Poor Match):** Missing most core requirements.

**Output Format:**
Respond ONLY with this JSON:
{{"skills_score": 8, "explanation": "Strengths: Python and SQL present. Gaps: Missing AWS."}}
""")

experience_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score a candidate's professional experience against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1. Identify required years of experience and seniority from the JD.
2. Compare to total relevant experience and roles in the CV.
3. Assign score using the rubric.
4. Write concise explanation highlighting matches and gaps.

**Scoring Rubric:**
- 9–10: Meets/exceeds requirements.
- 7–8: Close to required level.
- 4–6: Significantly below requirement.
- 1–3: Lacks relevant experience.

**Output Format:**
{{"experience_score": 6, "explanation": "Strengths: Relevant software roles. Gaps: 3 years vs. required 5."}}
""")

education_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score the candidate's educational background against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1. Identify specific degree requirements (e.g., “Bachelor’s in Computer Science”).
2. Compare to candidate’s education.
3. Score using rubric and justify.

**Scoring Rubric:**
- 9–10: Matches/exceeds education requirement.
- 7–8: Related field, slightly different.
- 4–6: Lower degree or unrelated.
- 1–3: Does not meet minimum requirement.

**Output Format:**
{{"education_score": 9, "explanation": "B.Tech in Computer Science matches perfectly."}}
""")

projects_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal to score how relevant the candidate's projects are to the job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1. Identify project-based skills relevant to the JD.
2. Evaluate presence and relevance of projects in CV.
3. Score using rubric below and justify.

**Scoring Rubric:**
- 9–10: Projects highly relevant.
- 7–8: Some relevant projects.
- 4–6: Minor relevance.
- 1–3: No relevant projects.

**Output Format:**
{{"projects_score": 10, "explanation": "Strong project relevance – built AI-based CV tool directly related to role."}}
""")

# -----------------------------
# State
# -----------------------------
class MatchingState(TypedDict):
    jd_text: str
    cv_text: str
    results: dict
    final_output: dict

# -----------------------------
# GEMINI CALLER (robust)
# -----------------------------
def call_gemini_api(prompt_text: str, category: str = "generic") -> str:
    """
    Call Gemini API with timeout and defensive handling. ALWAYS return a JSON string
    (so downstream json.loads() will succeed), or return the model text if it is valid JSON text.
    """
    # Dev shortcut: return mock responses (no network)
    if USE_MOCK_GEMINI or not GEMINI_API_KEY:
        print(f"[ai_matching] Using mock response for category '{category}' (USE_MOCK_GEMINI={USE_MOCK_GEMINI})")
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

    # attempt with a short timeout and a single retry
    for attempt in range(2):
        try:
            response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=15)
            print(f"[ai_matching] Gemini API status {response.status_code} (attempt {attempt+1}) for '{category}'")
            # non-200 -> return safe JSON describing error
            if response.status_code != 200:
                print("[ai_matching] Gemini non-200 response:", response.status_code, response.text[:600])
                return json.dumps({"score": 0, "explanation": f"Gemini non-200:{response.status_code}"})

            # try to decode JSON body
            try:
                resp_json = response.json()
            except Exception as e:
                print("[ai_matching] Failed to .json() decode Gemini response:", e)
                print("Raw response (truncated):", response.text[:2000])
                return json.dumps({"score": 0, "explanation": "Gemini returned non-JSON body"})

            # try to extract the text content where expected
            try:
                content = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                if not content or not content.strip():
                    return json.dumps({"score": 0, "explanation": "Empty content from Gemini"})
                # remove fences if present and return raw string (could be a JSON string or plain text)
                content = content.strip().lstrip("```json").rstrip("```").strip()
                return content
            except Exception as e:
                print("[ai_matching] Unexpected Gemini JSON shape:", e)
                print("Raw JSON (truncated):", json.dumps(resp_json)[:2000])
                return json.dumps({"score": 0, "explanation": "Unexpected Gemini response format"})
        except requests.Timeout:
            print("[ai_matching] Gemini request timed out (attempt", attempt+1, ")")
            if attempt == 1:
                return json.dumps({"score": 0, "explanation": "Gemini timeout"})
            time.sleep(1)
        except requests.RequestException as e:
            print("[ai_matching] Gemini request exception:", e)
            if attempt == 1:
                return json.dumps({"score": 0, "explanation": f"Gemini request exception: {str(e)[:200]}"})
            time.sleep(1)

    # fallback (should not reach)
    return json.dumps({"score": 0, "explanation": "Gemini call failed"})

# -----------------------------
# Node functions (defensive)
# -----------------------------
def skills_node(state: MatchingState):
    print("--- Running Skills Node ---")
    prompt_text = skills_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="skills")
    try:
        parsed = json.loads(response_str)
        if isinstance(parsed, dict):
            parsed.setdefault("skills_score", parsed.get("score", 0))
            parsed.setdefault("explanation", parsed.get("explanation", ""))
        else:
            raise ValueError("Parsed response not a JSON object")
    except Exception as e:
        print("[ai_matching] Failed to parse Gemini response for skills:", e)
        print("Raw response (truncated):", (response_str or "")[:2000])
        parsed = {"skills_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}

    results = state.get("results", {}) or {}
    results["skills"] = parsed
    state["results"] = results
    return {"results": results}

def experience_node(state: MatchingState):
    print("--- Running Experience Node ---")
    prompt_text = experience_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="experience")
    try:
        parsed = json.loads(response_str)
        if isinstance(parsed, dict):
            parsed.setdefault("experience_score", parsed.get("score", 0))
            parsed.setdefault("explanation", parsed.get("explanation", ""))
        else:
            raise ValueError("Parsed response not a JSON object")
    except Exception as e:
        print("[ai_matching] Failed to parse Gemini response for experience:", e)
        print("Raw response (truncated):", (response_str or "")[:2000])
        parsed = {"experience_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}

    results = state.get("results", {}) or {}
    results["experience"] = parsed
    state["results"] = results
    return {"results": results}

def education_node(state: MatchingState):
    print("--- Running Education Node ---")
    prompt_text = education_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="education")
    try:
        parsed = json.loads(response_str)
        if isinstance(parsed, dict):
            parsed.setdefault("education_score", parsed.get("score", 0))
            parsed.setdefault("explanation", parsed.get("explanation", ""))
        else:
            raise ValueError("Parsed response not a JSON object")
    except Exception as e:
        print("[ai_matching] Failed to parse Gemini response for education:", e)
        print("Raw response (truncated):", (response_str or "")[:2000])
        parsed = {"education_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}

    results = state.get("results", {}) or {}
    results["education"] = parsed
    state["results"] = results
    return {"results": results}

def projects_node(state: MatchingState):
    print("--- Running Projects Node ---")
    prompt_text = projects_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="projects")
    try:
        parsed = json.loads(response_str)
        if isinstance(parsed, dict):
            parsed.setdefault("projects_score", parsed.get("score", 0))
            parsed.setdefault("explanation", parsed.get("explanation", ""))
        else:
            raise ValueError("Parsed response not a JSON object")
    except Exception as e:
        print("[ai_matching] Failed to parse Gemini response for projects:", e)
        print("Raw response (truncated):", (response_str or "")[:2000])
        parsed = {"projects_score": 0, "explanation": "Invalid JSON from Gemini API or API error."}

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
            "skills": {
                "score": scores["skills"],
                "explanation": results.get("skills", {}).get("explanation", "") or ""
            },
            "experience": {
                "score": scores["experience"],
                "explanation": results.get("experience", {}).get("explanation", "") or ""
            },
            "education": {
                "score": scores["education"],
                "explanation": results.get("education", {}).get("explanation", "") or ""
            },
            "projects": {
                "score": scores["projects"],
                "explanation": results.get("projects", {}).get("explanation", "") or ""
            }
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
