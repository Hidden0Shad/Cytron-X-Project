from app import create_app
from app.models import db, User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    hashed_pw = generate_password_hash('Password123!')
    test_user = User(
        username='student_test', 
        email='student@school.edu', 
        password=hashed_pw, 
        role='Student'
    )
    db.session.add(test_user)
    db.session.commit()
    print("Test user created: student_test / Password123!")