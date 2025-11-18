import requests, json

API_KEY = "AIzaSyCu1pkK5OIqxWt_vzHPb6n60ycT8o0iI08"
url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={API_KEY}"

data = {
    "contents": [
        {"parts":[{"text":"Hello from test"}]}
    ]
}

r = requests.post(url, json=data)
print(r.status_code)
print(r.text)
