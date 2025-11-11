# backend/auth.py
import os
import time
from urllib.parse import urljoin
from functools import wraps

from flask import Blueprint, session, redirect, url_for, request, jsonify, current_app
from authlib.integrations.flask_client import OAuth
import jwt  

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("FLASK_SECRET_KEY") or "dev-jwt-secret"
JWT_ALGO = "HS256"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", 60 * 15))

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = OAuth()

# Setup OAuth client (call init_oauth(app) after creating the Flask app)
def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"}
    )

def login_required(f):
    """
    Decorator to protect routes. Works for both browser and AJAX/fetch clients.
    - For browser: redirects to /auth/login
    - For AJAX/fetch: returns JSON 401 with message
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # session-based user allowed
        user = session.get("user")
        if user:
            return f(*args, **kwargs)

        # also allow Bearer JWT for API calls
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
                # attach decoded user to request context if needed
                request._jwt_user = decoded.get("user")
                return f(*args, **kwargs)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "token_expired"}), 401
            except Exception:
                return jsonify({"error": "invalid_token"}), 401

        # Decide if request expects JSON (AJAX/fetch) or HTML (browser)
        wants_json = False
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            wants_json = True
        elif request.accept_mimetypes:
            wants_json = request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]

        if wants_json:
            return jsonify({"error": "login_required", "message": "Please sign in"}), 401

        # Otherwise redirect browser to backend login route (which will redirect to Google)
        login_url = url_for("auth.login", _external=True)
        return redirect(login_url)

    return decorated

# Helper: safe redirect back to frontend (configurable)
def frontend_url(path="/"):
    frontend = os.getenv("FRONTEND_URL") or current_app.config.get("FRONTEND_URL") or ""
    if frontend:
        return urljoin(frontend, path)
    return "/"

# Route: start login (redirects to Google)
@auth_bp.route("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    next_url = request.args.get("next")
    if next_url:
        session["next_url"] = next_url
    return oauth.google.authorize_redirect(redirect_uri)

# Route: OAuth callback - exchange code, build short JWT, redirect to frontend with token
@auth_bp.route("/callback")
def callback():
    try:
        token = oauth.google.authorize_access_token()
        userinfo = oauth.google.parse_id_token(token)
    except Exception as e:
        current_app.logger.exception("OAuth token exchange failed: %s", e)
        frontend = os.getenv("FRONTEND_URL") or current_app.config.get("FRONTEND_URL") or ""
        if frontend:
            return redirect(frontend + "/?auth_error=1")
        return redirect("/?auth_error=1")

    # minimal user payload
    user = {
        "sub": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }

    # Optionally store session if you want to support session-based flows too:
    # session['user'] = user

    # create a short-lived JWT payload
    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
        "user": user
    }

    token_jwt = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    # PyJWT may return bytes in older versions; ensure string
    if isinstance(token_jwt, bytes):
        token_jwt = token_jwt.decode("utf-8")

    frontend = os.getenv("FRONTEND_URL") or current_app.config.get("FRONTEND_URL") or ""
    if frontend:
        # Redirect to frontend with token in query parameter
        return redirect(f"{frontend}/?token={token_jwt}")

    # fallback simple response (dev)
    return f"Token: {token_jwt}"

# Alternate route name if your Google redirect URI points to /auth/google/callback
@auth_bp.route("/google/callback")
def google_callback():
    return callback()

# Logout
@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.pop("user", None)
    # For JWT-based flows the frontend should simply remove the token client-side.
    return redirect(frontend_url("/"))

# Endpoint used by frontend to get current user (supports session or Bearer JWT)
@auth_bp.route("/current_user", methods=["GET"])
def current_user():
    # 1) session-based user (backward compatible)
    user = session.get("user")
    if user:
        return jsonify({"user": user}), 200

    # 2) Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            user_from_token = payload.get("user")
            return jsonify({"user": user_from_token}), 200
        except jwt.ExpiredSignatureError:
            return jsonify({"user": None, "error": "token_expired"}), 401
        except Exception as e:
            current_app.logger.exception("JWT decode failed: %s", e)
            return jsonify({"user": None, "error": "invalid_token"}), 401

    # no auth found
    return jsonify({"user": None}), 200

# If you prefer /current_user at root (not under /auth), export a function to register that route on app
def register_current_user_route(app):
    @app.route("/current_user", methods=["GET"])
    def _current_user():
        # Use same behaviour: session first, then header JWT
        user = session.get("user")
        if user:
            return jsonify({"user": user}), 200

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
                user_from_token = payload.get("user")
                return jsonify({"user": user_from_token}), 200
            except jwt.ExpiredSignatureError:
                return jsonify({"user": None, "error": "token_expired"}), 401
            except Exception as e:
                current_app.logger.exception("JWT decode failed: %s", e)
                return jsonify({"user": None, "error": "invalid_token"}), 401

        return jsonify({"user": None}), 200
