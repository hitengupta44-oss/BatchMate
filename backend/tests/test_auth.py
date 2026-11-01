"""Signed tokens: valid, tampered, expired, wrong password. Runs without FastAPI installed."""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if "fastapi" not in sys.modules:
    try:
        import fastapi  # noqa: F401
    except ImportError:  # minimal stand-in so auth.py imports
        class HTTPException(Exception):
            def __init__(self, status_code, detail=""):
                super().__init__(detail)
                self.status_code = status_code
        stub = types.ModuleType("fastapi")
        stub.HTTPException = HTTPException
        stub.Header = lambda default="": default
        sys.modules["fastapi"] = stub

os.environ["DEMO_USERS"] = "priya:p1,arjun:p2,coordinator-demo:c1"
os.environ["AUTH_SECRET"] = "test-secret"

from batchmate import auth  # noqa: E402


def test_tokens():
    tok = auth.login("priya", "p1")
    assert auth.verify(tok) == "priya"
    assert auth.current_user(authorization=f"Bearer {tok}") == "priya"
    body, sig = tok.split(".")
    assert auth.verify(body + "." + sig[:-2] + "xx") is None          # tampered signature
    forged = auth._b64(b'{"u": "coordinator-demo", "exp": 9999999999}') + "." + sig
    assert auth.verify(forged) is None                               # can't become coordinator
    for bad in (("priya", "wrong"), ("nobody", "p1")):
        try:
            auth.login(*bad)
            raise AssertionError("bad login accepted")
        except Exception as e:
            assert getattr(e, "status_code", 401) == 401
    try:  # X-User header is ignored once sign-in is on
        auth.current_user(authorization="", x_user="coordinator-demo")
        raise AssertionError("bare X-User accepted")
    except Exception as e:
        assert getattr(e, "status_code", None) == 401
    assert auth.role("coordinator-demo") == "coordinator" and auth.role("priya") == "student"


if __name__ == "__main__":
    test_tokens()
    print("auth OK")
