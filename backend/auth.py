# backend/auth.py
import os
from flask import Blueprint, session, redirect, url_for, request, jsonify, current_app
from authlib.integrations.flask_client import OAuth
from urllib.parse import urljoin

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = OAuth()

# Setup OAuth client (we will init this in create_app or after blueprint registration)
def init_oauth(app):
    oauth.init_app(app)
    # Register Google client using env vars
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"}
    )

# Helper: safe redirect back to frontend (configurable)
def frontend_url(path="/"):
    frontend = os.getenv("FRONTEND_URL") or current_app.config.get("FRONTEND_URL") or ""
    if frontend:
        return urljoin(frontend, path)
    # fallback to root
    return "/"

# Route: start login
@auth_bp.route("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    # Save optional next param so after login you can redirect to a specific frontend path
    next_url = request.args.get("next")
    if next_url:
        session["next_url"] = next_url
    return oauth.google.authorize_redirect(redirect_uri)

# Route: callback
@auth_bp.route("/callback")
def callback():
    try:
        token = oauth.google.authorize_access_token()
        userinfo = oauth.google.parse_id_token(token)
    except Exception as e:
        # Redirect back to frontend with error if needed
        return redirect(frontend_url("/?auth_error=1"))

    # Example: store minimal user info in session
    user = {
        "id": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }

    session["user"] = user

    # Optional: redirect to saved next URL or to frontend profile
    next_url = session.pop("next_url", None)
    if next_url:
        # if next_url is relative, join with frontend root
        return redirect(frontend_url(next_url) if not next_url.startswith("http") else next_url)

    return redirect(frontend_url("/profile.html"))

# Alternate route name if your Google redirect URI points to /auth/google/callback
@auth_bp.route("/google/callback")
def google_callback():
    return callback()

# Logout
@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.pop("user", None)
    # After logout redirect back to frontend home
    return redirect(frontend_url("/"))

# Endpoint used by frontend to get current user
# Note: this path is not namespaced under /auth for easier access in main.js; you can also keep under /auth
@auth_bp.route("/current_user", methods=["GET"])
def current_user():
    user = session.get("user")
    if not user:
        return jsonify({"user": None}), 204
    return jsonify({"user": user})

# If you prefer /current_user at root (not under /auth), export a function to register that route on app
def register_current_user_route(app):
    @app.route("/current_user", methods=["GET"])
    def _current_user():
        user = session.get("user")
        if not user:
            return jsonify({"user": None}), 204
        return jsonify({"user": user})

