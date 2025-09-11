import os
import json
import shutil
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from backend.parsing import parse_cv
from backend.ai_matching import setup_graph

CVS_FOLDER = 'cvs_folder'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app = Flask(__name__)

# Ensure the folder for CVs exists
os.makedirs(CVS_FOLDER, exist_ok=True)

# One-Time Graph Compilation
print("🚀 Compiling the AI workflow graph... This happens only once!")
ai_graph_app = setup_graph()
print("✅ Graph compiled successfully.")

# checking if the files have an allowed extension
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Frontend Render Route
@app.route('/')
def index():
    return render_template('index.html')

# --- CV Upload Route ---
@app.route('/upload-cvs', methods=['POST'])
def upload_cvs():

    # Clear the CVs folder for a fresh session
    if os.path.exists(CVS_FOLDER):
        shutil.rmtree(CVS_FOLDER)
    os.makedirs(CVS_FOLDER)

    if 'files[]' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    files = request.files.getlist('files[]')
    uploaded_count = 0
    for file in files:
        if file and allowed_file(file.filename):
            # Secure the filename to prevent security issues
            filename = secure_filename(file.filename)
            file.save(os.path.join(CVS_FOLDER, filename))
            uploaded_count += 1
            
    return jsonify({
        'message': f'{uploaded_count} CVs uploaded successfully. Ready to match.'
    }), 200

# CV Matching Route
@app.route('/match-cvs', methods=['POST'])
def match_cvs():
    """Matches uploaded CVs against the provided job description."""
    data = request.get_json()
    if not data or 'job_description' not in data or not data['job_description'].strip():
        return jsonify({'error': 'Job description is required'}), 400

    job_description = data['job_description']
    results = []
    
    # Process each CV found in the folder
    for filename in os.listdir(CVS_FOLDER):
        filepath = os.path.join(CVS_FOLDER, filename)
        if os.path.isfile(filepath) and allowed_file(filename):
            try:
                # Parse the CV to get raw text
                parsed_text = parse_cv(filepath)

                # Prepare the initial state for the graph
                initial_state = {
                    "jd_text": job_description,
                    "cv_text": parsed_text,
                    "results": {},
                    "final_output": {}
                }
                
                # Invoke the pre-compiled graph
                final_state = ai_graph_app.invoke(initial_state)
                match_result = final_state.get("final_output", {})

                # Append the structured result
                if 'overall_score' in match_result:
                    results.append({
                        'filename': filename,
                        'overall_score': match_result['overall_score'],
                        'details': match_result['details']
                    })
                
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                # Append an error result for this specific file
                results.append({
                    'filename': filename,
                    'overall_score': 0,
                    'details': {
                        'skills': {'score': 0, 'explanation': f'Error: {e}'},
                        'experience': {'score': 0, 'explanation': f'Error: {e}'},
                        'education': {'score': 0, 'explanation': f'Error: {e}'},
                        'projects': {'score': 0, 'explanation': f'Error: {e}'}
                    }
                })

    if not results:
        return jsonify({'error': 'No valid CVs were processed.'}), 404

    # Sort results by score in descending order
    sorted_results = sorted(results, key=lambda x: x['overall_score'], reverse=True)
    return jsonify(sorted_results)

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)