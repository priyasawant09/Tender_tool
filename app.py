import os
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import json
from backend.parsing import parse_cv
from backend.ai_matching import get_ai_match
from backend.database import init_db, db_session, CV

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensuring the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# check if uploaded file has an allowed extension
def allowed_file(filename):
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')

# renders the main page
def index():
    return render_template('index.html')

@app.route('/upload-cv', methods=['POST'])

# uploads CVs and stores them in the database
def upload_cv():
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('files[]')
    errors = {}
    success = False

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # CV is parsed and stored in the database
            try:
                parsed_text = parse_cv(filepath)
                
                # checking if CV already exists
                existing_cv = CV.query.filter_by(filename=filename).first()
                if existing_cv:
                    existing_cv.content = parsed_text
                else:
                    new_cv = CV(filename=filename, content=parsed_text)
                    db_session.add(new_cv)
                
                db_session.commit()
                success = True
            except Exception as e:
                errors[file.filename] = str(e)

        else:
            errors[file.filename] = 'File type not allowed'

    if success and not errors:
        return jsonify({'message': 'CVs uploaded and processed successfully!'})
    elif success and errors:
        return jsonify({'message': 'Some CVs processed, but errors occurred.', 'errors': errors}), 207
    else:
        return jsonify({'error': 'Failed to process CVs', 'details': errors}), 500


@app.route('/match-cvs', methods=['POST'])

# matches CVs against a job description
def match_cvs():
    data = request.get_json()
    if not data or 'job_description' not in data:
        return jsonify({'error': 'Job description is required'}), 400

    job_description = data['job_description']
    
    # Retrieve all CVs from the database
    all_cvs = CV.query.all()
    if not all_cvs:
        return jsonify({'error': 'No CVs found in the database. Please upload some first.'}), 404

    results = []
    for cv in all_cvs:
        try:
            # AI matching result
            match_result_str = get_ai_match(cv.content, job_description)
            match_result = json.loads(match_result_str) # The AI returns a JSON string

            # Ensure the result has the expected keys
            if 'match_score' in match_result and 'explanation' in match_result:
                 results.append({
                    'filename': cv.filename,
                    'score': match_result['match_score'],
                    'explanation': match_result['explanation']
                })
            else:
                 print(f"Skipping result for {cv.filename} due to missing keys.")


        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from AI for CV {cv.filename}: {e}")
            print(f"Received string was: {match_result_str}")
            results.append({
                'filename': cv.filename,
                'score': 0,
                'explanation': f"An error occurred parsing the AI response. See console for details."
            })
        except Exception as e:
            print(f"Error matching CV {cv.filename}: {e}")
            # if any error occurs
            results.append({
                'filename': cv.filename,
                'score': 0,
                'explanation': f"An error occurred during analysis: {e}"
            })

    # Sort results by score in descending order
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    return jsonify(sorted_results)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == '__main__':
    # Initializes the database
    init_db()
    # Runs the app
    app.run(debug=True)
