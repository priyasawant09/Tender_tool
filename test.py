# make_test_jwt.py
import jwt, time
JWT_SECRET = "ad0467315831bcec6ccb779fe3578a63e33c66511b304d195dec90aaca7bab8c"   # replace with deployed JWT_SECRET if different
JWT_ALGO = "HS256"

now = int(time.time())
payload = {
    "iat": now,
    "exp": now + 60*60,   # 1 hour
    "user": {
        "sub": "test-user-1",
        "email": "you@example.com",
        "name": "Test User"
    }
}

token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
if isinstance(token, bytes):
    token = token.decode()
print(token)
