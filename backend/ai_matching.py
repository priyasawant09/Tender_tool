import os
import json
import requests
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from typing import TypedDict, Dict

# -----------------------------
# Gemini API Setup
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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
You are a meticulous AI Recruitment Analyst. Your goal is to score how relevant the candidate's projects are to the job description.

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
# STATE
# -----------------------------
class MatchingState(TypedDict):
    jd_text: str
    cv_text: str
    results: dict
    final_output: dict

# -----------------------------
# GEMINI CALLER
# -----------------------------
def call_gemini_api(prompt_text: str, category: str = "generic") -> str:
    """Helper to call Gemini API and return the model's response as JSON text."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print(f"⚠️ Warning: GEMINI_API_KEY not found. Returning mock data for '{category}'.")
        mock = {
            "skills": {"skills_score": 8, "explanation": "Mock: Python and SQL found."},
            "experience": {"experience_score": 6, "explanation": "Mock: 3 years vs required 5."},
            "education": {"education_score": 9, "explanation": "Mock: B.Tech in CS."},
            "projects": {"projects_score": 7, "explanation": "Mock: Relevant dashboard project."},
        }
        return json.dumps(mock.get(category, {"score": 0, "explanation": "Mock default"}))

    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        # Remove markdown fences if present
        return content.strip().lstrip("```json").rstrip("```").strip()
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"❌ Gemini API call failed for '{category}': {e}")
        return json.dumps({"score": 0, "explanation": f"API Error: {e}"})

# -----------------------------
# GRAPH NODES
# -----------------------------
def skills_node(state: MatchingState):
    print("--- Running Skills Node ---")
    prompt = skills_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    result = json.loads(call_gemini_api(prompt, "skills"))
    state["results"]["skills"] = result
    return {"results": state["results"]}

def experience_node(state: MatchingState):
    print("--- Running Experience Node ---")
    prompt = experience_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    result = json.loads(call_gemini_api(prompt, "experience"))
    state["results"]["experience"] = result
    return {"results": state["results"]}

def education_node(state: MatchingState):
    print("--- Running Education Node ---")
    prompt = education_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    result = json.loads(call_gemini_api(prompt, "education"))
    state["results"]["education"] = result
    return {"results": state["results"]}

def projects_node(state: MatchingState):
    print("--- Running Projects Node ---")
    prompt = projects_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    result = json.loads(call_gemini_api(prompt, "projects"))
    state["results"]["projects"] = result
    return {"results": state["results"]}

def aggregate_node(state: MatchingState):
    print("--- Running Aggregate Node ---")
    results = state.get("results", {})
    scores = {
        "skills": results.get("skills", {}).get("skills_score", 0),
        "experience": results.get("experience", {}).get("experience_score", 0),
        "education": results.get("education", {}).get("education_score", 0),
        "projects": results.get("projects", {}).get("projects_score", 0),
    }
    weights = {"skills": 0.3, "experience": 0.4, "education": 0.1, "projects": 0.2}
    overall_score = round(sum(scores[k] * weights[k] for k in scores), 1)
    final_output = {
        "overall_score": overall_score,
        "details": {
            "skills": {"score": scores["skills"], "explanation": results.get("skills", {}).get("explanation", "")},
            "experience": {"score": scores["experience"], "explanation": results.get("experience", {}).get("explanation", "")},
            "education": {"score": scores["education"], "explanation": results.get("education", {}).get("explanation", "")},
            "projects": {"score": scores["projects"], "explanation": results.get("projects", {}).get("explanation", "")},
        },
    }
    return {"final_output": final_output}

# -----------------------------
# GRAPH SETUP
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
