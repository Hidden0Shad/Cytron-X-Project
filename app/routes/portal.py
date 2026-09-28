from flask import Blueprint, request, jsonify
from app.models import db, AuditLog
from app.utils import require_auth

portal_bp = Blueprint('portal', __name__)

# Cleaned up: Strictly using 'Administrator' as fixed in the security audit
PERMISSIONS = {
    'Student': ['profile', 'student_records', 'assignments'],
    'Teacher': ['profile', 'student_records', 'assignments', 'gradebook', 'examination_results', 'teacher_functions'],
    'Administrator': ['profile', 'student_records', 'assignments', 'gradebook', 'examination_results', 'teacher_functions', 'user_management']
}

# Dummy data dictionary to satisfy the SRS requirements
MOCK_DATA = {
    'profile': {"status": "Active Profile", "message": "Welcome to your AuthShield 360 profile."},
    'student_records': [{"id": "S-001", "name": "Test Student", "status": "Enrolled"}],
    'assignments': [{"id": 101, "course": "Cybersecurity Fundamentals", "status": "Pending"}],
    'gradebook': [{"student_id": "S-001", "grade": "A"}],
    'examination_results': [{"student_id": "S-001", "score": 95, "remarks": "Excellent understanding of MFA."}],
    'teacher_functions': [
        {"function": "Mark Attendance", "status": "Available"},
        {"function": "Grade Assignments", "status": "Available"},
        {"function": "Post Examination Results", "status": "Available"}
    ],
    'user_management': [{"setting": "System Lockdown", "status": "Active"}]
}

# 1. FIXED: Added /<resource_name> so Flask captures the URL parameter from main.js
@portal_bp.route('/<resource_name>', methods=['GET'])
@require_auth
def get_portal_resource(resource_name):
    # role/username from verified session, not client headers
    session_row = request.current_session
    role = session_row.role
    username = session_row.username
    ip = request.remote_addr

    allowed = PERMISSIONS.get(role, [])
    
    if resource_name in allowed:
        # Fetch the dummy data for the requested resource
        data = MOCK_DATA.get(resource_name, [])
        return jsonify(data), 200

    # Log the unauthorized access attempt to satisfy SRS monitoring requirement
    entry = AuditLog(
        username=username, role=role, ip_address=ip,
        scenario='RBAC Verification', factor_used='Role Enforcement',
        action=f'Unauthorized attempt to access {resource_name}', status='FAILURE'
    )
    db.session.add(entry)
    db.session.commit()
    
    # Returns 403 Forbidden which the frontend will catch and display as an error
    return jsonify({'error': 'Unauthorized'}), 403

# Note: audit-log retrieval lives at GET /api/v1/logs/ (app/routes/logs.py),
# which is what main.js's fetchLogs() actually calls and is Administrator-only
# via @require_role. An earlier duplicate /logs route lived here too, with a
# different response shape; it was never called by the frontend and has been
# removed to avoid two diverging implementations of the same endpoint.
