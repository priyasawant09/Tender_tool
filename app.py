import os
import json
from flask import Flask, request, jsonify, render_template
from backend.parsing import parse_cv
from backend.ai_matching import get_ai_match

# Configuration
CVS_FOLDER = 'cvs_folder'  # folder where all your CVs are stored
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app = Flask(__name__)
os.makedirs(CVS_FOLDER, exist_ok=True)  # Ensure folder exists

# Check if file has allowed extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/match-cvs', methods=['POST'])
def match_cvs():
    """Matches CVs in the folder against a job description."""
    data = request.get_json()
    if not data or 'job_description' not in data:
        return jsonify({'error': 'Job description is required'}), 400

    job_description = data['job_description']
    results = []

    # Loop through all CVs in the folder
    for filename in os.listdir(CVS_FOLDER):
        if allowed_file(filename):
            filepath = os.path.join(CVS_FOLDER, filename)

            try:
                # Parse CV
                parsed_text = parse_cv(filepath)

                # Get AI match result
                match_result_str = get_ai_match(parsed_text, job_description)
                match_result = json.loads(match_result_str)

                # Validate AI response keys
                if 'match_score' in match_result and 'explanation' in match_result:
                    results.append({
                        'filename': filename,
                        'score': match_result['match_score'],
                        'explanation': match_result['explanation']
                    })
                else:
                    results.append({
                        'filename': filename,
                        'score': 0,
                        'explanation': "Invalid AI response format."
                    })

            except json.JSONDecodeError:
                results.append({
                    'filename': filename,
                    'score': 0,
                    'explanation': "Error decoding AI response."
                })
            except Exception as e:
                results.append({
                    'filename': filename,
                    'score': 0,
                    'explanation': f"Error processing CV: {e}"
                })

    if not results:
        return jsonify({'error': 'No valid CVs found in the folder.'}), 404

    # Sort results by score (highest first)
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)

    return jsonify(sorted_results)


if __name__ == '__main__':
    app.run(debug=True)
