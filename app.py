import os
import json
import shutil
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from backend.parsing import parse_cv
from backend.ai_matching import setup_graph
from backend.auth import auth_bp, init_oauth, login_required
from flask import session
from flask import redirect, url_for
from flask_cors import CORS


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")


CVS_FOLDER = 'cvs_folder'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app = Flask(__name__)

CORS(app, origins=["https://ghostwhite-fox-926923.hostingersite.com","http://localhost:5000"],supports_credentials=True)

app.config['SESSION_COOKIE_SAMESITE'] = "None"
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True


# Ensure the folder for CVs exists
os.makedirs(CVS_FOLDER, exist_ok=True)

# Configure app from environment variables (no dependency on config module)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY or os.getenv("FLASK_SECRET_KEY", "dev-secret")
app.config['GOOGLE_CLIENT_ID'] = GOOGLE_CLIENT_ID
app.config['GOOGLE_CLIENT_SECRET'] = GOOGLE_CLIENT_SECRET

# Optional OAuth redirect (only set if provided)
if OAUTH_REDIRECT_URI:
    app.config['OAUTH_REDIRECT_URI'] = OAUTH_REDIRECT_URI


init_oauth(app)
app.register_blueprint(auth_bp, url_prefix='/auth')



# One-Time Graph Compilation
print("🚀 Compiling the AI workflow graph... This happens only once!")
ai_graph_app = setup_graph()
print("✅ Graph compiled successfully.")

# checking if the files have an allowed extension
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Frontend Render Route

@app.route('/login')
def login_page_view():
    
    return render_template('login.html')

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login_page_view'))
    return render_template('index.html')

@app.route('/current_user')
def current_user():
    user = session.get('user')  
    if user:
        return jsonify({'user': user})
    return jsonify({'user': None}), 204

# --- CV Upload Route ---
@app.route('/upload-cvs', methods=['POST'])
@login_required
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
    from os import environ
    app.run(host="0.0.0.0", port=int(environ.get("PORT", 8000)))
   # app.run(debug=True)