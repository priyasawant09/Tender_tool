import requests
import json

API_KEY = "AIzaSyCu1pkK5OIqxWt_vzHPb6n60ycT8o0iI08"   # <-- replace with your key

url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={API_KEY}"

payload = {
    "contents": [
        {
            "parts": [
                {"text": "Say Hello World!"}
            ]
        }
    ]
}

headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Status Code:", response.status_code)
    print("---- Raw Response ----")
    print(response.text)

    if response.status_code == 200:
        result = response.json()
        output = result["candidates"][0]["content"]["parts"][0]["text"]
        print("\nGemini Output:", output)

except Exception as e:
    print("Error:", e)
