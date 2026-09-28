# AuthShield 360 — Backend

Flask backend for the AuthShield 360 fictional school portal (TechWiz 7,
Ethical Cyber Horizons category). Currently implements **Scenario 1:
Password-Only Authentication**, with failed-login lockout and server-verified
session tokens already in place ahead of Scenario 2 (OTP).

## Prerequisites
- Python 3.9+
- pip

## Setup
```bash
git clone <this-repo-url>
cd authshield-backends
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # copy the output...
# ...and paste it as SECRET_KEY's value inside your new .env

python run.py
```
The API starts at `http://127.0.0.1:5000`. The database (`instance/authshield.db`)
and its three fictional test accounts are created automatically on first run.

## Test accounts (fictional, per SRS constraints)
| Username      | Password      | Role          |
|---------------|---------------|---------------|
| student_user  | Student@123   | Student       |
| teacher_user  | Teacher@123   | Teacher       |
| admin_user    | Admin@123     | Administrator |

## How authentication works here
This is a JSON API, not a server-rendered site, so there's no browser
session cookie. Instead:

1. `POST /api/v1/auth/login-scenario-1` with a username/password.
2. On success, the response includes a `session_token`. **The server
   generates and stores this token itself** (in the `sessions` table); the
   client never gets to assert its own identity or role.
3. Every subsequent request to a protected route must include:
   ```
   Authorization: Bearer <session_token>
   ```
4. The server looks up the token, reads the *real* username/role from its
   own `Session` record, and uses that for every access decision. A client
   sending `X-User-Role: Administrator` or similar has no effect, that
   approach was tried earlier and removed after it turned out to be a full
   authentication bypass (see `docs/evidence/`).
5. `POST /api/v1/auth/logout` deletes the token so it can't be reused.
6. Tokens also expire on their own after `SESSION_TIMEOUT_MINUTES`
   (default 30, set in `.env`).

## API endpoints
| Method | Route | Auth required | Notes |
|--------|-------|---------------|-------|
| POST | `/api/v1/auth/login-scenario-1` | None | Locks account for 5 min after 5 failed attempts |
| POST | `/api/v1/auth/logout` | Bearer token | Invalidates the token |
| GET | `/api/v1/portal/data?resource=<name>` | Bearer token | Role checked server-side against the session |
| GET | `/api/v1/logs/` | Bearer token, Administrator only | Full authentication/audit history |

Valid `resource` values by role:
- Student: `student_records`, `assignments`
- Teacher: `student_records`, `assignments`, `gradebook`
- Administrator: all of the above, plus `admin_panel`

## What's implemented
- Password hashing (Werkzeug)
- Password-only login (Scenario 1)
- Failed-login lockout (5 attempts -> 5 minute lock)
- Server-verified session tokens (auth + role, never trusted from the client)
- Session logout / invalidation
- Role-based access control on portal resources and the audit log
- Full audit logging (`AuditLog` table) tagged by scenario, factor used, and outcome

## Not yet implemented (next phases)
- OTP / MFA (Scenario 2) — `OTPRecord` table exists, no route yet
- Email step-up verification (Scenario 3)
- A "remaining session time" endpoint for the frontend to show a countdown

## Security notes for the report
- `SECRET_KEY` lives in `.env` (git-ignored), never in source. Each teammate
  generates their own with the command above.
- `.env`, `instance/`, `*.db`, and `venv/` are all git-ignored.
- See `docs/evidence/identity-security-test-matrix.md` for the authorized
  test cycle that found and fixed a role-based access control bypass, and
  why an earlier header-based approach was rejected.
