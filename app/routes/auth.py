import os
import secrets
import datetime
import smtplib
from email.mime.text import MIMEText
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from app.models import db, User, OTPRecord, AuditLog
from app.utils import (
    create_session, get_current_session, invalidate_session, _extract_token,
    require_role, register_failed_attempt, reset_failed_attempts
)
from app.limiter import limiter

auth_bp = Blueprint('auth', __name__)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def log_event(username, role, ip, scenario, factor, action, status):
    entry = AuditLog(
        username=username, role=role, ip_address=ip,
        scenario=scenario, factor_used=factor, action=action, status=status
    )
    db.session.add(entry)
    db.session.commit()

def send_mailtrap_email(to_email, otp_code, is_stepup=False):
    """Sends OTPs to the Mailtrap Sandbox. Uses different subjects to distinguish Step 1 vs Step-Up."""
    sender = "security@authshield360.local"
    
    if is_stepup:
        subject = "AuthShield 360 - FINAL STEP-UP VERIFICATION"
        body = f"Your AuthShield 360 Step-Up Email OTP is: {otp_code}. This code expires in 5 minutes."
    else:
        subject = "AuthShield 360 - Login Verification"
        body = f"Your AuthShield 360 Primary OTP is: {otp_code}. This code expires in 5 minutes."

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to_email

    try:
        host = os.getenv('MAILTRAP_HOST', 'sandbox.smtp.mailtrap.io')
        port = int(os.getenv('MAILTRAP_PORT', 2525))
        with smtplib.SMTP(host, port) as server:
            server.login(os.getenv('MAILTRAP_USER'), os.getenv('MAILTRAP_PASS'))
            server.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Mock Delivery Error: {e}")
        return False

def deliver_otp(user, otp_code, label, is_stepup=False):
    """Deliver an OTP according to OTP_DELIVERY_MODE ('console' or 'mailtrap').
    Returns (ok, mode). Falls back to console if the mode is unset or unknown."""
    mode = (os.getenv('OTP_DELIVERY_MODE') or 'console').strip().lower()
    if mode == 'mailtrap':
        return send_mailtrap_email(user.email, otp_code, is_stepup=is_stepup), 'mailtrap'
    print(f"\n--- CONSOLE OTP ({label}) FOR {user.username}: {otp_code} ---\n")
    return True, 'console'


def generate_otp():
    """6-digit OTP from a cryptographically secure source."""
    return str(secrets.randbelow(900000) + 100000)


def issue_otp(user, otp_type):
    """Create a fresh OTP and invalidate any earlier unused ones of the same
    type, so only the most recently issued code is ever valid."""
    OTPRecord.query.filter_by(username=user.username, otp_type=otp_type, is_verified=False).delete()
    code = generate_otp()
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    db.session.add(OTPRecord(username=user.username, otp_type=otp_type, code=code, expires_at=expires))
    db.session.commit()
    return code


AUTH_FAIL_MSG = 'Invalid credentials, or the account is temporarily locked. Please try again later.'


def auth_failure():
    """One reply for wrong password, unknown user AND locked account, so the
    response cannot be used to confirm that a username exists. The real
    LOCKED state is still recorded in the audit log."""
    return jsonify({'error': AUTH_FAIL_MSG}), 401


def otp_failure(label):
    """Same idea for OTP steps: bad code, unknown user and locked account all
    look identical to the caller."""
    return jsonify({'error': f'Invalid or expired {label}, or the account is temporarily locked.'}), 400


# ==========================================
# SCENARIO 1: BASELINE PASSWORD ONLY
# ==========================================

@auth_bp.route('/login-scenario-1', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_1_login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        log_event(username, user.role, ip, 'Scenario 1', 'Password', 'Login Attempt on Locked Account', 'LOCKED')
        return auth_failure()

    if user and password and check_password_hash(user.password, password):
        reset_failed_attempts(user)

        log_event(username, user.role, ip, 'Scenario 1', 'Password', 'Baseline Password Login Successful', 'SUCCESS')
        token, expires_at = create_session(user.username, user.role)
        
        return jsonify({
            'message': 'Login Successful',
            'username': user.username,
            'role': user.role,
            'session_token': token,
            'expires_at': expires_at.isoformat() + 'Z'
        }), 200

    if user:
        user, attempts, just_locked = register_failed_attempt(user.username)
        if just_locked:
            log_event(username, user.role, ip, 'Scenario 1', 'Password', 'Max Failed Attempts - Account Locked', 'LOCKED')
        else:
            log_event(username, user.role, ip, 'Scenario 1', 'Password', f'Invalid Password Attempt ({attempts}/5)', 'FAILURE')
    else:
        log_event(username, 'Unknown', ip, 'Scenario 1', 'Password', 'Invalid User Login Attempt', 'FAILURE')

    return auth_failure()

# ==========================================
# SCENARIO 2: PASSWORD + MOCK EMAIL OTP
# ==========================================

@auth_bp.route('/login-scenario-2/step1', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_2_step1():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        log_event(username, user.role, ip, 'Scenario 2', 'Password', 'Login Attempt on Locked Account', 'LOCKED')
        return auth_failure()

    if user and password and check_password_hash(user.password, password):
        otp_code = issue_otp(user, 'mock_email')

        ok, mode = deliver_otp(user, otp_code, 'S2', is_stepup=False)
        if ok:
            if mode == 'mailtrap':
                log_event(username, user.role, ip, 'Scenario 2', 'Mock Email OTP', 'OTP Sent via Mailtrap', 'SUCCESS')
                return jsonify({'message': 'Password verified. Check your Mailtrap inbox for the OTP.'}), 200
            log_event(username, user.role, ip, 'Scenario 2', 'Console OTP', 'OTP Generated to Console', 'SUCCESS')
            return jsonify({'message': 'Password verified. Check server console for OTP.'}), 200
        return jsonify({'error': 'Failed to send OTP email.'}), 500

    if user:
        user, attempts, just_locked = register_failed_attempt(user.username)
        if just_locked:
            log_event(username, user.role, ip, 'Scenario 2', 'Password', 'Max Failed Attempts - Account Locked', 'LOCKED')
        else:
            log_event(username, user.role, ip, 'Scenario 2', 'Password', f'Invalid Password Attempt ({attempts}/5)', 'FAILURE')
    else:
        log_event(username, 'Unknown', ip, 'Scenario 2', 'Password', 'Invalid User Login Attempt', 'FAILURE')

    return auth_failure()


@auth_bp.route('/login-scenario-2/step2', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_2_step2():
    data = request.json or {}
    username = data.get('username')
    code = data.get('otp')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', 'OTP Attempt on Locked Account', 'LOCKED')
        return otp_failure('OTP code')
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='mock_email', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', 'Max Failed OTP Attempts - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', f'Invalid/Expired OTP ({attempts}/5)', 'FAILURE')
        return otp_failure('OTP code')

    otp_record.is_verified = True
    reset_failed_attempts(user)

    log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', 'MFA Login Successful', 'SUCCESS')
    token, expires_at = create_session(user.username, user.role)
    
    return jsonify({
        'message': 'MFA Login Successful', 
        'username': user.username, 
        'role': user.role,
        'session_token': token,
        'expires_at': expires_at.isoformat() + 'Z'
    }), 200

# ==========================================
# SCENARIO 3: PASSWORD + MOCK OTP + STEP-UP OTP
# ==========================================

@auth_bp.route('/login-scenario-3/step1', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_3_step1():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        log_event(username, user.role, ip, 'Scenario 3', 'Password', 'Login Attempt on Locked Account', 'LOCKED')
        return auth_failure()

    if user and password and check_password_hash(user.password, password):
        otp_code = issue_otp(user, 'scenario3_primary')

        ok, mode = deliver_otp(user, otp_code, 'S3 PRIMARY', is_stepup=False)
        if ok:
            log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', f'Primary OTP Sent via {mode.capitalize()}', 'SUCCESS')
            where = 'Mailtrap inbox' if mode == 'mailtrap' else 'server console'
            return jsonify({'message': f'Password verified. Check the {where} for your Primary OTP.'}), 200
        else:
            return jsonify({'error': 'Failed to send Primary OTP.'}), 500

    if user:
        user, attempts, just_locked = register_failed_attempt(user.username)
        if just_locked:
            log_event(username, user.role, ip, 'Scenario 3', 'Password', 'Max Failed Attempts - Account Locked', 'LOCKED')
        else:
            log_event(username, user.role, ip, 'Scenario 3', 'Password', f'Invalid Password ({attempts}/5)', 'FAILURE')
    else:
        log_event(username, 'Unknown', ip, 'Scenario 3', 'Password', 'Invalid User Login Attempt', 'FAILURE')

    return auth_failure()

@auth_bp.route('/login-scenario-3/step2', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_3_step2():
    data = request.json or {}
    username = data.get('username')
    code = data.get('otp')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        return otp_failure('Primary OTP')
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='scenario3_primary', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', 'Max Failed OTP - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', f'Invalid/Expired OTP ({attempts}/5)', 'FAILURE')
        return otp_failure('Primary OTP')

    otp_record.is_verified = True
    db.session.commit()
    log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', 'Primary OTP Verified', 'SUCCESS')

    # Generate and send the simulated Step-Up OTP via Mailtrap
    stepup_otp = issue_otp(user, 'scenario3_stepup')

    ok, mode = deliver_otp(user, stepup_otp, 'S3 STEP-UP', is_stepup=True)
    if ok:
        log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', f'Step-Up OTP Sent via {mode.capitalize()}', 'SUCCESS')
        where = 'Mailtrap inbox' if mode == 'mailtrap' else 'server console'
        return jsonify({'message': f'Primary OTP verified. Check the {where} for the Final Step-Up OTP.'}), 200
    else:
        return jsonify({'error': 'Failed to send Step-Up OTP.'}), 500

@auth_bp.route('/login-scenario-3/step3', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_3_step3():
    data = request.json or {}
    username = data.get('username')
    code = data.get('otp')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        return otp_failure('Step-Up OTP')
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='scenario3_stepup', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', 'Max Failed Step-Up - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', f'Invalid/Expired Step-Up OTP ({attempts}/5)', 'FAILURE')
        return otp_failure('Step-Up OTP')

    otp_record.is_verified = True
    reset_failed_attempts(user)

    log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', 'Step-Up MFA Login Successful', 'SUCCESS')
    token, expires_at = create_session(user.username, user.role)
    
    return jsonify({
        'message': 'Step-Up MFA Login Successful', 
        'username': user.username, 
        'role': user.role,
        'session_token': token,
        'expires_at': expires_at.isoformat() + 'Z'
    }), 200

# ==========================================
# LOGOUT AND SESSION INVALIDATION
# ==========================================

@auth_bp.route('/logout', methods=['POST'])
def logout():
    token = _extract_token()
    session_row = get_current_session()

    if session_row is None:
        return jsonify({'error': 'No active session to log out'}), 401

    log_event(session_row.username, session_row.role, request.remote_addr,
              'Session', 'Logout', 'User logged out', 'SUCCESS')
    invalidate_session(token)
    return jsonify({'message': 'Logged out successfully'}), 200

# ==========================================
# RBAC TESTING ENDPOINT
# ==========================================

@auth_bp.route('/test-admin', methods=['GET'])
@require_role('Administrator', 'Teacher') 
def test_admin_route():
    return jsonify({'message': 'Welcome to the restricted area! You have Administrator/Teacher access.'}), 200
