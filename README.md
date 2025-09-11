# AI-Based CV Matching using LLM

## Project Overview

This project automates the process of matching CVs with job descriptions using AI. It parses CVs in PDF or DOCX formats, evaluates each CV against a job description using a Large Language Model (LLM), and generates a score out of 10 along with a brief explanation. This application is designed to help HR teams shortlist candidates efficiently and accurately.

## Key Features

- Accurate parsing and extraction of CVs in PDF and DOCX formats.

- AI-based CV-JD matching using Gemini LLM API.

- Scoring system (0–10) with explanations for each CV.

- User-friendly interface built with HTML, CSS, and JavaScript.

- Flask backend for smooth execution and rendering results.

## Tech Stack

- Frontend: HTML, CSS, JavaScript

- Backend: Python, Flask

- LLM: Gemini API
- Frameworks: Langgraph

- File Handling: PDF and DOCX parsing using fitz and docx

## System Workflow

- Make a cvs_folder in the root directory.
- Store the CVs which you want to analyze in the cvs_folder.

- Enter job description in the UI.

- parsing.py extracts relevant information from CVs.

- ai_matching.py uses langgraph and compares CVs with JD using Gemini LLM API.

- Flask backend (app.py) renders results on frontend (index.html).

- Display CV scores and reasoning for each candidate.

## Challenges Faced

- Parsing PDFs and DOCX files was initially inconsistent.

- AI matching required strict prompt engineering for accuracy.

- Local model training caused system crashes due to high resource usage.

- Resolved by using an API-based approach with Gemini LLM.

## Project Outcomes

- Fully functional AI-based CV matching application.

- Provides numerical scores and detailed explanations for each CV.

- Handles multiple CV formats.

- Ready for potential deployment in HR workflows.

## Folder Structure

Of course, here is the project structure formatted for a README file.

```
AI-Based-CV-Matching-Tool/
├── backend/
│   ├── __init__.py
│   ├── ai_matching.py      # Gemini LLM matching logic using Langgraph
│   └── parsing.py          # CV parsing and extraction
├── cvs_folder/             # Folder to store all CVs
├── templates/
│   └── index.html          # Frontend UI
├── venv/                   # Python virtual environment
├── .gitignore
├── app.py                  # Flask backend entry point
├── config.py               # Configuration file (e.g., API keys)
└── requirements.txt        # Python dependencies
```


## How to Run
1. Clone the repository
- git clone https://github.com/your-username/ai-cv-matching.git
cd ai-cv-matching

2. Set up Python environment
### Create a virtual environment
- python -m venv venv

### Activate it
#### For Windows
- venv\Scripts\activate
#### For macOS/Linux
- source venv/bin/activate

3. Install dependencies
- pip install -r requirements.txt

4. Configure Gemini API

- Create a .env file in the project root and create an Gemini API key from google AI studio and place the api key in .env file as:

#### GEMINI_API_KEY=your_api_key_here

5. Prepare CVs folder

- Add PDF or DOCX CVs in the cvs_folder.

6. Run the Flask app
- python app.py

- Open http://127.0.0.1:5000/ in a browser to access the UI.

7. Match CVs

- Enter job description in the UI.

- Click Match CVs to get scores and explanations for each CV.

## Future Enhancements

- Multi-language CV support.

- Integration with real-time job portals.

- Advanced analytics for candidate insights.
