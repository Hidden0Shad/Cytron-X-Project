from werkzeug.security import generate_password_hash
# Adjust this import based on your actual app structure (e.g., from main import app, db)
from app.models import db, User 
from run import app 

with app.app_context():
    # Check if admin already exists
    existing_admin = User.query.filter_by(username='admin_boss').first()
    if not existing_admin:
        new_admin = User(
            username='admin_boss',
            email='admin@authshield.local',
            password=generate_password_hash('AdminPass99!'),
            role='Administrator'  # must match PERMISSIONS/RBAC keys exactly, not 'Admin'
        )
        db.session.add(new_admin)
        db.session.commit()
        print("Success! Admin user 'admin_boss' created with password 'AdminPass99!'")
    else:
        print("Admin user already exists!")
        