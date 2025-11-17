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

**Analysis Steps:**
1.  From the Job Description, identify the 4-6 most critical technical skills, programming languages, and tools required. These are the 'core requirements'.
2.  Meticulously scan the CV to find direct evidence for each of the core requirements.
3.  Based on the scoring rubric below, assign a score.
4.  Write a concise explanation justifying your score, explicitly mentioning 2-3 key skills the candidate possesses and any critical skills that are missing.
5.  The explanation should clearly list strengths and gaps using bullet points.
                                             
**Scoring Rubric:**
- **9-10 (Excellent Match):** Candidate demonstrates strong evidence for all core requirements.
- **7-8 (Good Match):** Candidate meets most of the core requirements.
- **4-6 (Fair Match):** Candidate meets some requirements but has significant gaps.
- **1-3 (Poor Match):** Candidate is missing most or all of the core requirements.

**Output Format:**
Your final response MUST BE a single, clean JSON object and nothing else. Do not add any text or markdown before or after it.

**Example Output:**
{{"skills_score": 8, "explanation": "Strengths: Strong evidence for Python and SQL as required. Gaps: Missing experience with AWS."}}

IMPORTANT: Respond with ONLY a single valid JSON object and nothing else. No markdown, no backticks, no explanation. If you cannot produce valid JSON, reply exactly: {"error":"no_json_found"}.
                                                                                          
""")

experience_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score a candidate's professional experience against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1.  From the Job Description, determine the required years of experience (e.g., "5+ years") and the expected seniority or role type (e.g., "Senior Software Engineer").
2.  From the CV, calculate the candidate's total years of relevant professional experience and check if their job titles align with the required seniority.
3.  Based on the scoring rubric below, assign a score.
4.  Write a concise explanation justifying your score, directly comparing the candidate's years of experience and role relevance to what the job requires.
5.  The explanation should clearly list strengths and gaps using bullet points.

**Scoring Rubric:**
- **9-10 (Excellent Match):** Experience level and role relevance meet or exceed all requirements.
- **7-8 (Good Match):** Experience level is close to the requirement, and roles are highly relevant.
- **4-6 (Fair Match):** Experience is significantly less than required OR roles are not fully relevant.
- **1-3 (Poor Match):** Lacks relevant professional experience.

**Output Format:**
Your final response MUST BE a single, clean JSON object and nothing else. Do not add any text or markdown before or after it.

**Example Output:**
{{"experience_score": 6, "explanation": "Strengths: Roles in software development are relevant. Gaps: Candidate has 3 years of experience, while the JD requires 5+ years."}}
                                                 
IMPORTANT: Respond with ONLY a single valid JSON object and nothing else. No markdown, no backticks, no explanation. If you cannot produce valid JSON, reply exactly: {"error":"no_json_found"}.

""")

education_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to objectively score a candidate's educational background against a job description.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1.  From the Job Description, identify any specific degree requirements (e.g., "Bachelor's in Computer Science").
2.  If no specific education is required, your default score should be 10.
3.  Scan the CV for the required academic qualifications.
4.  Based on the scoring rubric below, assign a score.
5.  Write a concise explanation justifying your score.
6.  The explanation should clearly list strengths and gaps using bullet points.

**Scoring Rubric:**
- **9-10 (Excellent Match):** Perfectly matches or exceeds the educational requirements, or no specific education is required.
- **7-8 (Good Match):** Degree is in a related field but not the exact one specified.
- **4-6 (Fair Match):** Possesses a degree, but not at the level or in the field required.
- **1-3 (Poor Match):** Does not meet the minimum educational requirements.

**Output Format:**
Your final response MUST BE a single, clean JSON object and nothing else. Do not add any text or markdown before or after it.

**Example Output:**
{{"education_score": 9, "explanation": "Candidate holds a B.Tech in Computer Science, which matches the job requirement."}}

IMPORTANT: Respond with ONLY a single valid JSON object and nothing else. No markdown, no backticks, no explanation. If you cannot produce valid JSON, reply exactly: {"error":"no_json_found"}.

    """)

projects_prompt = PromptTemplate.from_template("""
You are a meticulous AI Recruitment Analyst. Your goal is to evaluate how a candidate's project work demonstrates practical application of the skills required for a job.

**Job Description:**
```{jd_text}```

**Candidate's CV:**
```{cv_text}```

**Analysis Steps:**
1.  From the Job Description, infer the key practical skills that projects/assignments could demonstrate (e.g., building web apps, data analysis).
2.  Scan the CV for a "Projects" or "Assignments" section. If no projects/assignments are listed, assign a low score (1-3).
3.  Evaluate the listed projects/assignments for their relevance to the job's practical requirements.
4.  Based on the scoring rubric below, assign a score.
5.  Write a concise explanation justifying your score, mentioning a specific project if it is highly relevant.
6.  The explanation should clearly list strengths and gaps using bullet points.

**Scoring Rubric:**
- **9-10 (Excellent Match):** Projects/assignments are highly relevant and provide strong, direct evidence of the candidate's ability to perform the job.
- **7-8 (Good Match):** Projects/assignments are relevant and demonstrate some of the key skills required.
- **4-6 (Fair Match):** Projects/assignments are present but have low relevance to the job's requirements.
- **1-3 (Poor Match):** No projects/assignments are listed, or they are completely irrelevant.

**Output Format:**
Your final response MUST BE a single, clean JSON object and nothing else. Do not add any text or markdown before or after it.

**Example Output:**
{{"projects_score": 10, "explanation": "Strengths: The 'AI-based CV Matching Tool' project is extremely relevant and demonstrates direct, hands-on experience for this role."}}

IMPORTANT: Respond with ONLY a single valid JSON object and nothing else. No markdown, no backticks, no explanation. If you cannot produce valid JSON, reply exactly: {"error":"no_json_found"}.
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
# Helpers
# -----------------------------
def extract_json_object_from_text(text: str):
    """
    Find a balanced { ... } JSON object in noisy text and return the parsed object if found.
    Returns None if no valid JSON object can be extracted.
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    # strip code fences
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
                        if not best or len(cand) > len(best[0]):
                            best = (cand, parsed)
                    except Exception:
                        pass
                    break
    return best[1] if best else None

# -----------------------------
# Robust Gemini Caller
# -----------------------------
def call_gemini_api(prompt_text: str, category: str = "generic") -> str:
    """
    Call Gemini with the *minimal valid* request shape that works:
      { "contents": [ { "parts": [ { "text": "..." } ] } ] }

    Returns the model text (unparsed). On error, returns a JSON string describing the error
    so downstream parsing won't crash.
    """
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

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    except requests.Timeout:
        print(f"[ai_matching] Gemini timeout for '{category}'")
        return json.dumps({"score": 0, "explanation": "Gemini timeout"})
    except requests.RequestException as e:
        print(f"[ai_matching] Gemini request exception for '{category}': {e}")
        return json.dumps({"score": 0, "explanation": f"Gemini request exception: {str(e)[:200]}"})

    # Non-200 -> return safe JSON string with snippet
    if resp.status_code != 200:
        body = resp.text[:2000]
        print(f"[ai_matching] Gemini non-200: {resp.status_code} Body (truncated):")
        print(body)
        return json.dumps({"score": 0, "explanation": f"Gemini non-200:{resp.status_code}", "raw": body[:1000]})

    # Try to extract text candidate
    try:
        resp_json = resp.json()
        text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("[ai_matching] Failed to parse Gemini JSON:", e)
        print("Raw response (truncated):", resp.text[:2000])
        return json.dumps({"score": 0, "explanation": "Gemini returned unexpected structure", "raw": resp.text[:1000]})

    # return the raw model text (caller will attempt to extract JSON from it)
    return text.strip()


# -----------------------------
# Helpers: safe parsing wrapper
# -----------------------------
def _safe_parse_response(response_str: str, category_key: str):
    # Try direct JSON
    try:
        parsed = json.loads(response_str)
        return parsed
    except Exception:
        pass

    # Try extract JSON object from noisy text
    try:
        parsed = extract_json_object_from_text(response_str)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # fallback
    return {f"{category_key}_score": 0, "explanation": "Invalid JSON from Gemini API or API error.", "raw": (response_str or "")[:1000]}

# -----------------------------
# Summarization node
# -----------------------------
def summarize_cv_node(state: MatchingState):
    print("--- Running Summarization Node ---")
    cv_text = state.get("cv_text", "") or ""
    # limit pre-summarize size to avoid huge prompt in the summary step
    if len(cv_text) > 25000:
        cv_text = cv_text[:25000]

    summary_prompt = f"""
You are an expert HR assistant. Summarize the CV into a compact structured summary (max 3000 characters).

Extract ONLY:
- Skills (comma separated)
- Total years of experience and key roles
- Education (degrees)
- Major relevant projects
- Specific port/terminal/IWT related experience sections (if present)

Return plain text summary only, no JSON. Keep it concise.
CV:
{cv_text}
"""
    response = call_gemini_api(summary_prompt, category="summary")
    # call_gemini_api tries to return JSON strings for some categories; ensure we keep plain text summary
    # If we received a JSON object, extract readable text or join fields; otherwise use returned text
    try:
        parsed = json.loads(response)
        # If summary returned as object, create a readable text summary
        if isinstance(parsed, dict):
            # join key: value pairs into short summary string
            parts = []
            for k, v in parsed.items():
                parts.append(f"{k}: {v}")
            summary_text = " | ".join(parts)[:4000]
        else:
            summary_text = str(parsed)[:4000]
    except Exception:
        summary_text = str(response)[:4000]

    # store summary in state for downstream nodes
    return {"cv_summary": summary_text}

# -----------------------------
# Node functions (use summary fallback)
# -----------------------------
def skills_node(state: MatchingState):
    print("--- Running Skills Node ---")
    cv_text = state.get("cv_summary") or state.get("cv_text") or ""
    if len(cv_text) > 12000:
        cv_text = cv_text[:12000]
    jd_text = state.get("jd_text", "") or ""

    try:
        prompt_text = skills_prompt.format(jd_text=jd_text, cv_text=cv_text)
    except Exception as e:
        print("[ai_matching] skills_prompt.format() failed:", e)
        prompt_text = getattr(skills_prompt, "template", "Job: {jd_text}\nCV: {cv_text}").format(jd_text=jd_text[:2000], cv_text=cv_text[:2000])

    response_str = call_gemini_api(prompt_text, category="skills")
    parsed = _safe_parse_response(response_str, "skills")

    if isinstance(parsed, dict):
        parsed.setdefault("skills_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"skills_score": 0, "explanation": "Unexpected response type from Gemini."}

    current_results = state.get("results", {}) or {}
    current_results["skills"] = parsed
    state["results"] = current_results
    return {"results": current_results}

def experience_node(state: MatchingState):
    print("--- Running Experience Node ---")
    cv_text = state.get("cv_summary") or state.get("cv_text") or ""
    if len(cv_text) > 12000:
        cv_text = cv_text[:12000]
    jd_text = state.get("jd_text", "") or ""

    try:
        prompt_text = experience_prompt.format(jd_text=jd_text, cv_text=cv_text)
    except Exception as e:
        print("[ai_matching] experience_prompt.format() failed:", e)
        prompt_text = f"Job: {jd_text[:2000]}\nCV: {cv_text[:2000]}"

    response_str = call_gemini_api(prompt_text, category="experience")
    parsed = _safe_parse_response(response_str, "experience")

    if isinstance(parsed, dict):
        parsed.setdefault("experience_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"experience_score": 0, "explanation": "Unexpected response type from Gemini."}

    current_results = state.get("results", {}) or {}
    current_results["experience"] = parsed
    state["results"] = current_results
    return {"results": current_results}

def education_node(state: MatchingState):
    print("--- Running Education Node ---")
    cv_text = state.get("cv_summary") or state.get("cv_text") or ""
    if len(cv_text) > 12000:
        cv_text = cv_text[:12000]
    jd_text = state.get("jd_text", "") or ""

    try:
        prompt_text = education_prompt.format(jd_text=jd_text, cv_text=cv_text)
    except Exception as e:
        print("[ai_matching] education_prompt.format() failed:", e)
        prompt_text = f"Job: {jd_text[:2000]}\nCV: {cv_text[:2000]}"

    response_str = call_gemini_api(prompt_text, category="education")
    parsed = _safe_parse_response(response_str, "education")

    if isinstance(parsed, dict):
        parsed.setdefault("education_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"education_score": 0, "explanation": "Unexpected response type from Gemini."}

    current_results = state.get("results", {}) or {}
    current_results["education"] = parsed
    state["results"] = current_results
    return {"results": current_results}

def projects_node(state: MatchingState):
    print("--- Running Projects Node ---")
    cv_text = state.get("cv_summary") or state.get("cv_text") or ""
    if len(cv_text) > 12000:
        cv_text = cv_text[:12000]
    jd_text = state.get("jd_text", "") or ""

    try:
        prompt_text = projects_prompt.format(jd_text=jd_text, cv_text=cv_text)
    except Exception as e:
        print("[ai_matching] projects_prompt.format() failed:", e)
        prompt_text = f"Job: {jd_text[:2000]}\nCV: {cv_text[:2000]}"

    response_str = call_gemini_api(prompt_text, category="projects")
    parsed = _safe_parse_response(response_str, "projects")

    if isinstance(parsed, dict):
        parsed.setdefault("projects_score", parsed.get("score", 0))
        parsed.setdefault("explanation", parsed.get("explanation", ""))
    else:
        parsed = {"projects_score": 0, "explanation": "Unexpected response type from Gemini."}

    current_results = state.get("results", {}) or {}
    current_results["projects"] = parsed
    state["results"] = current_results
    return {"results": current_results}

# -----------------------------
# Aggregate node
# -----------------------------
def aggregate_node(state: MatchingState):
    print("--- Running Aggregate Node ---")
    results = state.get("results", {}) or {}

    def safe_score(obj, key, fallback=0):
        try:
            val = obj.get(key, fallback)
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str) and val.replace('.', '', 1).isdigit():
                return float(val) if '.' in val else int(val)
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
    workflow.add_node("summarize", summarize_cv_node)
    workflow.add_node("skills", skills_node)
    workflow.add_node("experience", experience_node)
    workflow.add_node("education", education_node)
    workflow.add_node("projects", projects_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("summarize")
    workflow.add_edge("summarize", "skills")
    workflow.add_edge("skills", "experience")
    workflow.add_edge("experience", "education")
    workflow.add_edge("education", "projects")
    workflow.add_edge("projects", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile()
