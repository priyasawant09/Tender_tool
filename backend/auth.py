# backend/auth.py
from flask import Blueprint, url_for, redirect, session, request, current_app
from authlib.integrations.flask_client import OAuth
from functools import wraps

# Create a blueprint
auth_bp = Blueprint('auth', __name__)
oauth = OAuth()


# --- OAuth initialization ---
def init_oauth(app):
    
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )


# --- Login required decorator ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# --- Google Login Route ---
@auth_bp.route('/login')
def login():
    next_url = request.args.get('next') or url_for('index', _external=True)
    session['oauth_next'] = next_url

    redirect_uri = url_for('auth.authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/authorize')
def authorize():
    # Exchange code for access token
    token = oauth.google.authorize_access_token()

    resp = oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo')
    userinfo = resp.json()

    # Store user in session
    session['user'] = {
        'sub': userinfo.get('sub'),
        'email': userinfo.get('email'),
        'name': userinfo.get('name'),
        'picture': userinfo.get('picture')
    }

    # Redirect back to where they started (or to index)
    next_url = session.pop('oauth_next', None) or url_for('index')
    return redirect(next_url)


# --- Logout ---
@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))
