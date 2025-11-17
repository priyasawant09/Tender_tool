# app.py
import os
import shutil
import traceback
import concurrent.futures
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.utils import secure_filename
from flask_cors import CORS, cross_origin

from backend.parsing import parse_cv
from backend.ai_matching import setup_graph  # patched ai_matching.py must be deployed
from backend.auth import auth_bp, init_oauth, login_required, register_current_user_route

# Environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL") or "https://ghostwhite-fox-926923.hostingersite.com"

CVS_FOLDER = 'cvs_folder'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

# Flask App Setup
app = Flask(__name__, static_folder="frontend_hostinger/Static", template_folder="templates")
app.config['SECRET_KEY'] = FLASK_SECRET_KEY or "dev-secret-change-me"

IS_PRODUCTION = os.getenv("ENV") == "production" or os.getenv("FLASK_ENV") == "production"
app.config.update({
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_SECURE": True if IS_PRODUCTION else False,
    "SESSION_COOKIE_HTTPONLY": True,
    "PREFERRED_URL_SCHEME": "https"
})

# Ensure CV folder exists
os.makedirs(CVS_FOLDER, exist_ok=True)

# CORS (global)
ALLOWED_ORIGINS = [
    "https://ghostwhite-fox-926923.hostingersite.com",
    "http://localhost:5000",
]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False,
     allow_headers=["Content-Type", "Authorization"], methods=["GET", "POST", "OPTIONS"])

# Fallback to always set CORS headers (ensures even error responses include them)
@app.after_request
def always_add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# OAuth Setup
app.config['GOOGLE_CLIENT_ID'] = os.getenv("GOOGLE_CLIENT_ID")
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv("GOOGLE_CLIENT_SECRET")
if OAUTH_REDIRECT_URI:
    app.config['OAUTH_REDIRECT_URI'] = OAUTH_REDIRECT_URI

init_oauth(app)
app.register_blueprint(auth_bp, url_prefix="/auth")
register_current_user_route(app)

# One-time Graph Compilation (done at startup)
print("Compiling AI workflow graph... This happens only once.")
ai_graph_app = setup_graph()
print("Graph compiled successfully.")

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Small wrapper to run graph.invoke() with timeout (returns None on timeout)
def invoke_graph_with_timeout(graph_app, initial_state, timeout=60):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
            fut = exe.submit(graph_app.invoke, initial_state)
            return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"[app] Graph.invoke timed out after {timeout} seconds")
        return None
    except Exception as e:
        print("[app] Exception invoking graph:", e)
        traceback.print_exc()
        return None

# Frontend Routes / API Mode
SERVE_TEMPLATES = os.getenv("SERVE_TEMPLATES", "false").lower() in ("1", "true", "yes")

@app.route('/')
def index():
    if SERVE_TEMPLATES:
        if 'user' not in session:
            return redirect(url_for('login_page_view'))
        return render_template('index.html')
    return jsonify({"status": "ok", "message": "Backend API running. Use /auth/login for Google Sign-In."}), 200

@app.route('/login')
def login_page_view():
    if SERVE_TEMPLATES:
        return render_template('login.html')
    return jsonify({"message": "Use /auth/login to start Google sign-in"}), 200

@app.route('/current_user', methods=['GET', 'OPTIONS'])
def current_user():
    user = session.get('user')
    return jsonify({'user': user}), 200 if user else 401

# CV Upload endpoint
@app.route('/upload-cvs', methods=['POST'])

def upload_cvs():
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

    return jsonify({'message': f'{uploaded_count} CV(s) uploaded successfully. Ready for matching.'}), 200

# Match endpoint: accepts OPTIONS and POST; cross_origin outermost so CORS headers set even if login_required denies
@app.route('/match-cvs', methods=['POST', 'OPTIONS'])
@cross_origin(origin="https://ghostwhite-fox-926923.hostingersite.com", methods=["POST", "OPTIONS"])

def match_cvs():
    try:
        if request.method == "OPTIONS":
            return jsonify({"ok": True}), 200

        data = request.get_json()
        if not data or not data.get('job_description', '').strip():
            return jsonify({'error': 'Job description is required'}), 400

        job_description = data['job_description']
        print("[app] Incoming match request. JD len:", len(job_description))

        results = []
        for filename in os.listdir(CVS_FOLDER):
            filepath = os.path.join(CVS_FOLDER, filename)
            if os.path.isfile(filepath) and allowed_file(filename):
                try:
                    parsed_text = parse_cv(filepath)
                    print(f"[app] Parsed {filename}: {len(parsed_text)} chars")
                    if not parsed_text or not parsed_text.strip():
                        print(f"[app] Skipping {filename}: empty parse result")
                        continue

                    initial_state = {
                        "jd_text": job_description,
                        "cv_text": parsed_text,
                        "results": {},
                        "final_output": {}
                    }

                    # Use timeout wrapper to avoid infinite blocking
                    final_state = invoke_graph_with_timeout(ai_graph_app, initial_state, timeout=60)
                    if final_state is None:
                        print(f"[app] Graph timed out or failed for {filename}")
                        # append a safe failed result for this file
                        results.append({
                            'filename': filename,
                            'overall_score': 0,
                            'details': {
                                'skills': {'score': 0, 'explanation': 'Graph timeout or error'},
                                'experience': {'score': 0, 'explanation': 'Graph timeout or error'},
                                'education': {'score': 0, 'explanation': 'Graph timeout or error'},
                                'projects': {'score': 0, 'explanation': 'Graph timeout or error'},
                            }
                        })
                        continue

                    match_result = final_state.get("final_output", {}) if isinstance(final_state, dict) else {}
                    if 'overall_score' in match_result:
                        results.append({
                            'filename': filename,
                            'overall_score': match_result['overall_score'],
                            'details': match_result['details']
                        })
                    else:
                        # no score returned for this CV
                        results.append({
                            'filename': filename,
                            'overall_score': 0,
                            'details': {
                                'skills': {'score': 0, 'explanation': 'No score returned'},
                                'experience': {'score': 0, 'explanation': 'No score returned'},
                                'education': {'score': 0, 'explanation': 'No score returned'},
                                'projects': {'score': 0, 'explanation': 'No score returned'},
                            }
                        })

                except Exception as e:
                    print(f"[app] Error processing {filename}: {e}")
                    traceback.print_exc()
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

    except Exception as e:
        print("[app] FATAL error in /match-cvs:", e)
        traceback.print_exc()
        return jsonify({"error": "internal server error", "detail": str(e)}), 500
    

@app.route("/healthz")
def healthz():
    return jsonify({"status":"ok"}), 200


if __name__ == '__main__':
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Flask server on port {port} (Production: {IS_PRODUCTION})")
    # For Render: consider starting with a single worker in the service settings or the start command:
    # gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120
    app.run(host="0.0.0.0", port=port, debug=not IS_PRODUCTION)
