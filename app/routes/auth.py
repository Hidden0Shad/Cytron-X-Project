import os
import random
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
        return jsonify({'error': 'Account is temporarily locked.'}), 429

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

    return jsonify({'error': 'Invalid credentials'}), 401

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
        return jsonify({'error': 'Account is temporarily locked.'}), 429

    if user and password and check_password_hash(user.password, password):
        otp_code = str(random.randint(100000, 999999))
        expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        
        otp_entry = OTPRecord(username=user.username, otp_type='mock_email', code=otp_code, expires_at=expires)
        db.session.add(otp_entry)
        db.session.commit()

        delivery_mode = os.getenv('OTP_DELIVERY_MODE', 'console')
        
        if delivery_mode == 'mailtrap':
            if send_mailtrap_email(user.email, otp_code, is_stepup=False):
                log_event(username, user.role, ip, 'Scenario 2', 'Mock Email OTP', 'OTP Sent via Mailtrap', 'SUCCESS')
                return jsonify({'message': 'Password verified. Check your Mailtrap inbox for the OTP.'}), 200
            else:
                return jsonify({'error': 'Failed to send OTP email.'}), 500
        else:
            print(f"\n--- CONSOLE OTP FOR {username}: {otp_code} ---\n")
            log_event(username, user.role, ip, 'Scenario 2', 'Console OTP', 'OTP Generated to Console', 'SUCCESS')
            return jsonify({'message': 'Password verified. Check server console for OTP.'}), 200

    if user:
        user, attempts, just_locked = register_failed_attempt(user.username)
        if just_locked:
            log_event(username, user.role, ip, 'Scenario 2', 'Password', 'Max Failed Attempts - Account Locked', 'LOCKED')
        else:
            log_event(username, user.role, ip, 'Scenario 2', 'Password', f'Invalid Password Attempt ({attempts}/5)', 'FAILURE')
    else:
        log_event(username, 'Unknown', ip, 'Scenario 2', 'Password', 'Invalid User Login Attempt', 'FAILURE')

    return jsonify({'error': 'Invalid credentials'}), 401


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
        return jsonify({'error': 'Account is temporarily locked.'}), 429
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='mock_email', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', 'Max Failed OTP Attempts - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 2', 'OTP Verifier', f'Invalid/Expired OTP ({attempts}/5)', 'FAILURE')
        return jsonify({'error': 'Invalid or expired OTP code'}), 400

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
        return jsonify({'error': 'Account is temporarily locked.'}), 429

    if user and password and check_password_hash(user.password, password):
        otp_code = str(random.randint(100000, 999999))
        expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        
        otp_entry = OTPRecord(username=user.username, otp_type='scenario3_primary', code=otp_code, expires_at=expires)
        db.session.add(otp_entry)
        db.session.commit()

        if send_mailtrap_email(user.email, otp_code, is_stepup=False):
            log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', 'Primary OTP Sent', 'SUCCESS')
            return jsonify({'message': 'Password verified. Check Mailtrap for your Primary OTP.'}), 200
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

    return jsonify({'error': 'Invalid credentials'}), 401

@auth_bp.route('/login-scenario-3/step2', methods=['POST'])
@limiter.limit("20 per minute")
def scenario_3_step2():
    data = request.json or {}
    username = data.get('username')
    code = data.get('otp')
    ip = request.remote_addr

    user = User.query.filter_by(username=username).first()

    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        return jsonify({'error': 'Account is temporarily locked.'}), 429
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='scenario3_primary', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', 'Max Failed OTP - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', f'Invalid/Expired OTP ({attempts}/5)', 'FAILURE')
        return jsonify({'error': 'Invalid or expired Primary OTP'}), 400

    otp_record.is_verified = True
    db.session.commit()
    log_event(username, user.role, ip, 'Scenario 3', 'Primary OTP', 'Primary OTP Verified', 'SUCCESS')

    # Generate and send the simulated Step-Up OTP via Mailtrap
    stepup_otp = str(random.randint(100000, 999999))
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    stepup_entry = OTPRecord(username=user.username, otp_type='scenario3_stepup', code=stepup_otp, expires_at=expires)
    db.session.add(stepup_entry)
    db.session.commit()

    if send_mailtrap_email(user.email, stepup_otp, is_stepup=True):
        log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', f'Step-Up Mock OTP sent', 'SUCCESS')
        return jsonify({'message': f'Primary OTP verified. Check Mailtrap for the Final Step-Up OTP.'}), 200
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
        return jsonify({'error': 'Account is temporarily locked.'}), 429
    
    otp_record = OTPRecord.query.filter_by(username=username, otp_type='scenario3_stepup', code=code, is_verified=False)\
                                 .order_by(OTPRecord.id.desc()).first()

    if not otp_record or otp_record.expires_at < datetime.datetime.utcnow():
        if user:
            user, attempts, just_locked = register_failed_attempt(user.username)
            if just_locked:
                log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', 'Max Failed Step-Up - Account Locked', 'LOCKED')
            else:
                log_event(username, user.role, ip, 'Scenario 3', 'Email Step-Up', f'Invalid/Expired Step-Up OTP ({attempts}/5)', 'FAILURE')
        return jsonify({'error': 'Invalid or expired Step-Up OTP'}), 400

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
