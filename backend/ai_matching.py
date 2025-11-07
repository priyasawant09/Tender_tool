import os
import json
import requests
from config import GEMINI_API_KEY
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from typing import TypedDict, Dict

# API URL for the Gemini model
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"


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
""")

# State
class MatchingState(TypedDict):
    jd_text: str
    cv_text: str
    results: dict
    final_output: dict

# Helper function to call API
def call_gemini_api(prompt_text: str, category: str = "generic") -> str:
    """Helper function to call Gemini API and return a JSON string response."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print(f"Warning: GEMINI_API_KEY not found. Returning mock data for '{category}'.")
        mock_responses = {
            "skills": json.dumps({"skills_score": 8, "explanation": "Mock: Strong in Python, Java."}),
            "experience": json.dumps({"experience_score": 6, "explanation": "Mock: 3 years exp, requires 5."}),
            "education": json.dumps({"education_score": 9, "explanation": "Mock: B.Tech in CS matches."}),
            "projects": json.dumps({"projects_score": 7, "explanation": "Mock: Good final year project."}),
        }
        return mock_responses.get(category, json.dumps({"score": 0, "explanation": "Mock default"}))

    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        content = result['candidates'][0]['content']['parts'][0]['text']
        # Clean the response to ensure it's a valid JSON string
        return content.strip().lstrip('```json').rstrip('```').strip()
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"API call failed for '{category}': {e}")
        return json.dumps({"score": 0, "explanation": f"API Error: {e}"})

# Node functions
def skills_node(state: MatchingState):
    print("--- Running Skills Node ---")
    prompt_text = skills_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="skills")
    current_results = state.get("results", {})
    current_results["skills"] = json.loads(response_str)
    return {"results": current_results}

def experience_node(state: MatchingState):
    print("--- Running Experience Node ---")
    prompt_text = experience_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="experience")
    current_results = state.get("results", {})
    current_results["experience"] = json.loads(response_str)
    return {"results": current_results}

def education_node(state: MatchingState):
    print("--- Running Education Node ---")
    prompt_text = education_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="education")
    current_results = state.get("results", {})
    current_results["education"] = json.loads(response_str)
    return {"results": current_results}

def projects_node(state: MatchingState):
    print("--- Running Projects Node ---")
    prompt_text = projects_prompt.format(jd_text=state["jd_text"], cv_text=state["cv_text"])
    response_str = call_gemini_api(prompt_text, category="projects")
    current_results = state.get("results", {})
    current_results["projects"] = json.loads(response_str)
    return {"results": current_results}

def aggregate_node(state: MatchingState):
    """
    Aggregates scores and formats the final output with the
    nested structure expected by the frontend.
    """
    print("--- Running Aggregate Node ---")
    results = state.get("results", {})
    
    scores = {
        "skills": results.get("skills", {}).get("skills_score", 0),
        "experience": results.get("experience", {}).get("experience_score", 0),
        "education": results.get("education", {}).get("education_score", 0),
        "projects": results.get("projects", {}).get("projects_score", 0),
    }
    
    weights = {"skills": 0.3, "experience": 0.4, "education": 0.1, "projects": 0.2}
    overall_score = round(sum(scores[cat] * weights[cat] for cat in scores), 1)

    # Build the nested dictionary that the JavaScript expects.
    final_output = {
        "overall_score": overall_score,
        "details": {
            "skills": {
                "score": scores["skills"],
                "explanation": results.get("skills", {}).get("explanation", "N/A")
            },
            "experience": {
                "score": scores["experience"],
                "explanation": results.get("experience", {}).get("explanation", "N/A")
            },
            "education": {
                "score": scores["education"],
                "explanation": results.get("education", {}).get("explanation", "N/A")
            },
            "projects": {
                "score": scores["projects"],
                "explanation": results.get("projects", {}).get("explanation", "N/A")
            }
        }
    }
    return {"final_output": final_output}

# Graph setup
def setup_graph():
    workflow = StateGraph(MatchingState)
    workflow.add_node("skills", skills_node)
    workflow.add_node("experience", experience_node)
    workflow.add_node("education", education_node)
    workflow.add_node("projects", projects_node)
    workflow.add_node("aggregate", aggregate_node)

    # Correct sequential workflow
    workflow.set_entry_point("skills")
    workflow.add_edge("skills", "experience")
    workflow.add_edge("experience", "education")
    workflow.add_edge("education", "projects")
    workflow.add_edge("projects", "aggregate")
    workflow.add_edge("aggregate", END)

    return workflow.compile()