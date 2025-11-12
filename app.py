import os
import shutil
from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for
)
from werkzeug.utils import secure_filename
from backend.parsing import parse_cv
from backend.ai_matching import setup_graph
from backend.auth import auth_bp, init_oauth, login_required, register_current_user_route
from flask_cors import CORS

# Environment Variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL") or "https://ghostwhite-fox-926923.hostingersite.com"

CVS_FOLDER = 'cvs_folder'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

# Flask App Setup
app = Flask(__name__, static_folder="frontend_hostinger/Static", template_folder="templates")
app.config['SECRET_KEY'] = FLASK_SECRET_KEY or "dev-secret-change-me"


# Session and Security Configuration
IS_PRODUCTION = os.getenv("ENV") == "production" or os.getenv("FLASK_ENV") == "production"
app.config.update({
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_SECURE": True if IS_PRODUCTION else False,
    "SESSION_COOKIE_HTTPONLY": True,
    "PREFERRED_URL_SCHEME": "https"

    
})

# Ensure CV folder exists
os.makedirs(CVS_FOLDER, exist_ok=True)

# CORS Configuration
allowed_origins = [
    FRONTEND_URL,
    "https://ghostwhite-fox-926923.hostingersite.com",
    "http://localhost:5000"
]
CORS(app, origins=allowed_origins, supports_credentials=True, allow_headers=['Content-Type','Authorization'])


# OAuth Setup
app.config['GOOGLE_CLIENT_ID'] = GOOGLE_CLIENT_ID
app.config['GOOGLE_CLIENT_SECRET'] = GOOGLE_CLIENT_SECRET
if OAUTH_REDIRECT_URI:
    app.config['OAUTH_REDIRECT_URI'] = OAUTH_REDIRECT_URI

init_oauth(app)
app.register_blueprint(auth_bp, url_prefix="/auth")
register_current_user_route(app)

# One-time Graph Compilation
print("Compiling AI workflow graph... This happens only once.")
ai_graph_app = setup_graph()
print("Graph compiled successfully.")

# Helper Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Frontend Routes / API Mode
SERVE_TEMPLATES = os.getenv("SERVE_TEMPLATES", "false").lower() in ("1", "true", "yes")

@app.route('/')
def index():
    """
    In production (Hostinger frontend): returns a JSON message.
    In dev mode (SERVE_TEMPLATES=true): serves index.html for local testing.
    """
    if SERVE_TEMPLATES:
        if 'user' not in session:
            return redirect(url_for('login_page_view'))
        return render_template('index.html')

    return jsonify({
        "status": "ok",
        "message": "Backend API running. Use /auth/login for Google Sign-In."
    }), 200

@app.route('/login')
def login_page_view():
    if SERVE_TEMPLATES:
        return render_template('login.html')
    return jsonify({"message": "Use /auth/login to start Google sign-in"}), 200

@app.route('/current_user')
def current_user():
    """Return logged-in user info or None."""
    user = session.get('user')
    return jsonify({'user': user}), 200

# CV Upload API
@app.route('/upload-cvs', methods=['POST'])
@login_required
def upload_cvs():
    """Upload and save CVs."""
    # Clear folder before new upload
    if os.path.exists(CVS_FOLDER):
        shutil.rmtree(CVS_FOLDER)
    os.makedirs(CVS_FOLDER)

    if 'files[]' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    files = request.files.getlist('files[]')
    uploaded_count = 0
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(CVS_FOLDER, filename))
            uploaded_count += 1

    return jsonify({
        'message': f'{uploaded_count} CV(s) uploaded successfully. Ready for matching.'
    }), 200

# CV Matching API
@app.route('/match-cvs', methods=['POST'])
@login_required
def match_cvs():
    """Match uploaded CVs against the job description."""
    data = request.get_json()
    if not data or not data.get('job_description', '').strip():
        return jsonify({'error': 'Job description is required'}), 400

    job_description = data['job_description']
    results = []

    for filename in os.listdir(CVS_FOLDER):
        filepath = os.path.join(CVS_FOLDER, filename)
        if os.path.isfile(filepath) and allowed_file(filename):
            try:
                parsed_text = parse_cv(filepath)
                initial_state = {
                    "jd_text": job_description,
                    "cv_text": parsed_text,
                    "results": {},
                    "final_output": {}
                }
                final_state = ai_graph_app.invoke(initial_state)
                match_result = final_state.get("final_output", {})

                if 'overall_score' in match_result:
                    results.append({
                        'filename': filename,
                        'overall_score': match_result['overall_score'],
                        'details': match_result['details']
                    })
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                results.append({
                    'filename': filename,
                    'overall_score': 0,
                    'details': {
                        'skills': {'score': 0, 'explanation': str(e)},
                        'experience': {'score': 0, 'explanation': str(e)},
                        'education': {'score': 0, 'explanation': str(e)},
                        'projects': {'score': 0, 'explanation': str(e)},
                    }
                })

    if not results:
        return jsonify({'error': 'No valid CVs processed.'}), 404

    sorted_results = sorted(results, key=lambda x: x['overall_score'], reverse=True)
    return jsonify(sorted_results), 200

# Run Flask App
if __name__ == '__main__':
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Flask server on port {port} (Production: {IS_PRODUCTION})")
    app.run(host="0.0.0.0", port=port, debug=not IS_PRODUCTION)
