from flask import Blueprint, jsonify
from app.models import AuditLog
from app.utils import require_role

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/', methods=['GET'])
@require_role('Administrator')
def fetch_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    results = [{
        'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'username': l.username,
        'role': l.role,
        'scenario': l.scenario,
        'status': l.status
    } for l in logs]
    # Returned as a bare array, not {'logs': [...]}: main.js does
    # `logs.forEach(...)` directly on the parsed response body.
    return jsonify(results), 200
