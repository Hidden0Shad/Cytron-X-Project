# AuthShield 360

A Flask web app and JSON API for the fictional "Cyber Hall" school portal
(TechWiz 7, Ethical Cyber Horizons category). It demonstrates and lets you
compare three authentication designs, with server-side sessions, role-based
access control, account lockout, rate limiting and a full audit log.

| Scenario | Login flow |
|----------|------------|
| 1. Password Only | Password |
| 2. Password + OTP | Password, then a 6-digit email OTP |
| 3. Step-Up MFA | Password, then a primary OTP, then a second step-up OTP |

All accounts, emails and phone numbers are fictional.

## Prerequisites
- Python 3.9+
- pip
- Optional: a free [Mailtrap](https://mailtrap.io) sandbox inbox, only if you want OTPs delivered as mock emails instead of printed to the terminal

## Setup
```bash
git clone https://github.com/Hidden0Shad/Cytron-X-Project.git
cd Cytron-X-Project
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
Open `http://127.0.0.1:5000`. The database (`instance/authshield.db`) and the
three seed accounts below are created automatically on first run.

## Configuration (`.env`)
`.env` is git-ignored. Restart the server after editing it, because it is
only read at startup.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | insecure fallback | Flask secret. Always set your own. |
| `SESSION_TIMEOUT_MINUTES` | `30` | Lifetime of a session token |
| `OTP_DELIVERY_MODE` | `console` | `console` prints OTPs in the server terminal. `mailtrap` sends them to your Mailtrap inbox. Unset or unknown values fall back to `console`. |
| `MAILTRAP_HOST` / `MAILTRAP_PORT` | `sandbox.smtp.mailtrap.io` / `2525` | Mailtrap SMTP server |
| `MAILTRAP_USER` / `MAILTRAP_PASS` | none | Mailtrap credentials. Required only in `mailtrap` mode. |
| `FLASK_HOST` | `127.0.0.1` | Set to `0.0.0.0` so other machines (e.g. a Kali VM) can reach the app |
| `FLASK_DEBUG` | `0` | `1` enables the Werkzeug debugger. Local use only. |

### OTP delivery
In `console` mode the OTP appears in the terminal running `python run.py`:
```
--- CONSOLE OTP (S2) FOR student_user: 123456 ---
--- CONSOLE OTP (S3 PRIMARY) FOR student_user: 123456 ---
--- CONSOLE OTP (S3 STEP-UP) FOR student_user: 123456 ---
```
In `mailtrap` mode the OTP goes to the inbox of the account's email address
via your sandbox. Primary and step-up emails have different subjects
("Login Verification" and "FINAL STEP-UP VERIFICATION"). OTPs are 6 digits,
generated with `secrets`, and expire after 5 minutes. Requesting a new OTP
invalidates any earlier unused one of the same type.

## Test accounts (seeded on first run)
| Username | Password | Role | Email |
|----------|----------|------|-------|
| `student_user` | `Student@123` | Student | student@school.edu |
| `teacher_user` | `Teacher@123` | Teacher | teacher@school.edu |
| `admin_user` | `Admin@123` | Administrator | admin@school.edu |

Seeding only happens when the users table is empty. To reset everything,
stop the server and delete the `instance/` folder.

These passwords are for local testing only. Change them before any real deployment.

## Using the web app
| Page | URL |
|------|-----|
| Home | `/` |
| School portal (login and dashboard) | `/portal` |
| Register, Platform, Solutions, Resources, Company, Calendar | `/register`, `/platform`, `/solutions`, `/resources`, `/company`, `/calendar` |

On `/portal`, pick a tab for the scenario you want to test (Password Only,
Password + OTP, Step-Up MFA) and log in. For the OTP scenarios the form
switches to the OTP field after the password step. After login, the sidebar
shows the modules and the **Security Logs** view (Administrator only).
The session token is kept in the browser's `localStorage` and sent as a
Bearer token on every request.

## How authentication works
1. The client completes the login steps for a scenario (see the API table).
2. On the final step, the server creates a random token, stores it in the
   `sessions` table with the user's real role and an expiry time, and returns
   it as `session_token`.
3. Every protected request must send:
   ```
   Authorization: Bearer <session_token>
   ```
   (`X-Session-Token` is also accepted.)
4. The server looks the token up and uses the username and role from its own
   `Session` record for every access decision. Client-supplied role headers
   are ignored. An earlier header-based design was a full authentication
   bypass and was removed.
5. `POST /api/v1/auth/logout` deletes the token. Tokens also expire on their own.

## API endpoints
| Method | Route | Auth | Notes |
|--------|-------|------|-------|
| POST | `/api/v1/auth/login-scenario-1` | None | Body: `username`, `password`. Returns a session token. |
| POST | `/api/v1/auth/login-scenario-2/step1` | None | Body: `username`, `password`. Sends the OTP. |
| POST | `/api/v1/auth/login-scenario-2/step2` | None | Body: `username`, `otp`. Returns a session token. |
| POST | `/api/v1/auth/login-scenario-3/step1` | None | Body: `username`, `password`. Sends the primary OTP. |
| POST | `/api/v1/auth/login-scenario-3/step2` | None | Body: `username`, `otp` (primary). Sends the step-up OTP. |
| POST | `/api/v1/auth/login-scenario-3/step3` | None | Body: `username`, `otp` (step-up). Returns a session token. |
| POST | `/api/v1/auth/logout` | Bearer | Invalidates the token |
| GET | `/api/v1/portal/<resource>` | Bearer | Role checked against the session (see below) |
| GET | `/api/v1/logs/` | Bearer, Administrator | Audit log, newest first |
| GET | `/api/v1/auth/test-admin` | Bearer, Teacher or Administrator | RBAC test endpoint |

Successful logins return:
```json
{ "message": "...", "username": "...", "role": "...", "session_token": "...", "expires_at": "..." }
```

### Role permissions for `/api/v1/portal/<resource>`
| Resource | Student | Teacher | Administrator |
|----------|:-------:|:-------:|:-------------:|
| `profile` | yes | yes | yes |
| `student_records` | yes | yes | yes |
| `assignments` | yes | yes | yes |
| `gradebook` | no | yes | yes |
| `examination_results` | no | yes | yes |
| `teacher_functions` | no | yes | yes |
| `user_management` | no | no | yes |

A request for a resource the role does not have returns `403` and writes an
`Unauthorized attempt` entry to the audit log. A missing or expired token
returns `401`.

## Security controls
- **Password hashing** with Werkzeug.
- **Account lockout**: 5 failed attempts (wrong password or wrong OTP) lock the account for 5 minutes. The counter is shared across the steps of a login and is incremented atomically in the database, so parallel brute-force requests cannot skip the lockout. A successful full login resets it.
- **No username enumeration**: wrong password, unknown user and locked account all return the same `401` message on password steps. OTP steps return an equally generic `400`. The real state (`LOCKED`, `FAILURE`) is only visible in the audit log. Note that a correct password on a locked account is also rejected during the lock window.
- **Rate limiting**: 20 requests per minute per IP on each login route, returning `429` with a JSON error. Counters are stored in memory and reset when the server restarts.
- **Server-verified sessions** with expiry and logout.
- **Role-based access control** enforced on the server.
- **Audit log** (`audit_logs` table): every login step, lockout, logout and unauthorized access attempt is recorded with timestamp, username, role, IP, scenario, factor used, action and status (`SUCCESS`, `FAILURE`, `LOCKED`). Administrators can view it in the portal or at `/api/v1/logs/`.
- **SQLite tuned for concurrency** (WAL mode and a busy timeout), so concurrent attack tests do not crash the dev server.
- **Secure defaults**: the server binds to `127.0.0.1` with the debugger off, and `.env`, `instance/`, `*.db` and `venv/` are git-ignored.

## Testing from another machine (e.g. Kali)
By default the server only accepts connections from the same machine. To
attack it from a Kali VM:

1. In `.env`, set `FLASK_HOST=0.0.0.0` and leave `FLASK_DEBUG` unset, then restart.
2. Find the host machine's IP and make sure port 5000 is allowed through its firewall.
3. Point your tools at `http://<host-ip>:5000/api/v1/auth/login-scenario-1` (or the Scenario 2 and 3 routes).

Only test systems you own or have written permission to test. When finished,
remove `FLASK_HOST` so the server goes back to localhost only.

What to expect when you test:
- After 5 wrong attempts the account locks for 5 minutes. Tools see only `401`, with no status change at the moment of lockout. The proof is in the audit log (`Max Failed Attempts - Account Locked`, status `LOCKED`) and in the fact that the correct password is also rejected during the lock window.
- Sending more than 20 requests per minute from one IP returns `429`, which is the rate limiter, not the lockout.
- Keep your own screenshots, tool output and logs from these runs as evidence. `**/evidence/` is git-ignored, so store them in `docs/evidence/` locally or move them somewhere tracked if you want to submit them with the repo.

## Project structure
```
run.py                  App entry point and page routes
config.py               Loads .env and app config
create_user.py          Adds student_test / Password123!
create_teacher.py       Adds teacher_test / TeacherPass99!
create_admin.py         Adds admin_boss / AdminPass99!
app/
  __init__.py           App factory, DB setup, seed users, 429 handler
  models.py             User, OTPRecord, AuditLog, Session
  limiter.py            Flask-Limiter setup
  utils.py              Session helpers, lockout logic, auth decorators
  routes/auth.py        Login scenarios 1-3, logout, OTP delivery
  routes/portal.py      Role-protected portal resources
  routes/logs.py        Admin-only audit log
  templates/            HTML pages (authshield.html is the portal)
  static/               CSS, JS (main.js drives the portal), images
```
The three `create_*.py` scripts add extra test accounts. Run them from the
project root, for example `python create_admin.py`. `create_user.py` has no
duplicate check, so run it only once.

## Troubleshooting
- **Scenario 2 or 3 says the OTP failed to send**: check `OTP_DELIVERY_MODE`. For `console`, no other setup is needed. For `mailtrap`, make sure `MAILTRAP_USER` and `MAILTRAP_PASS` are filled in. The terminal prints the exact SMTP error. Restart after changing `.env`.
- **No OTP appears anywhere**: in console mode look at the terminal running `run.py`, not the browser.
- **"Invalid credentials, or the account is temporarily locked"**: this one message covers both cases on purpose. Wait 5 minutes, or delete `instance/` to reset the database.
- **Login seems to fail after many tries**: you may have hit the rate limit (`429`). Wait a minute.

## Known limitations
- Rate limit counters are in memory (Flask-Limiter prints a warning at startup). A production setup would use Redis or similar.
- The session token is stored in `localStorage`, which is readable by any script injected into the page.
- CORS is open to all origins.
- `/api/v1/auth/test-admin` is a testing endpoint and should be removed for production.
- `datetime.utcnow()` is deprecated in newer Python versions.
- Seed passwords and the `SECRET_KEY` fallback are for local testing only.
