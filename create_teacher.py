from werkzeug.security import generate_password_hash
from app.models import db, User 
from run import app 

with app.app_context():
    # Check if teacher already exists
    existing_teacher = User.query.filter_by(username='teacher_test').first()
    if not existing_teacher:
        new_teacher = User(
            username='teacher_test',
            email='teacher@authshield.local',
            password=generate_password_hash('TeacherPass99!'),
            role='Teacher'
        )
        db.session.add(new_teacher)
        db.session.commit()
        print("Success! Teacher user 'teacher_test' created with password 'TeacherPass99!'")
    else:
        print("Teacher user already exists!")