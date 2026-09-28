from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy import event
from werkzeug.security import generate_password_hash
from app.models import db, User
from config import Config
from app.limiter import limiter

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    limiter.init_app(app)

    # SQLite has no real row locking: by default a second writer that shows
    # up while another transaction is open fails immediately with
    # "database is locked" instead of waiting, which is exactly what a
    # concurrent brute-force test (many login/OTP attempts hitting the DB
    # at once) triggers, and that unhandled OperationalError is what
    # crashed the dev server under concurrent load. WAL mode lets readers
    # and writers coexist and busy_timeout makes a second writer wait
    # instead of erroring, so this is only applied for sqlite.
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        with app.app_context():
            @event.listens_for(db.engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=15000")
                cursor.close()

    with app.app_context():
        db.create_all()
        seed_users()

    from app.routes.auth import auth_bp
    from app.routes.portal import portal_bp
    from app.routes.logs import logs_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(portal_bp, url_prefix='/api/v1/portal')
    app.register_blueprint(logs_bp, url_prefix='/api/v1/logs')

    # Flask-Limiter's default 429 response is a plain HTML error page.
    # main.js always calls res.json() on the response, which throws on
    # HTML and surfaces as a generic "Server connection failed" instead
    # of the real "too many attempts" message.
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({'error': 'Too many requests. Please wait a moment and try again.'}), 429

    return app

def seed_users():
    if User.query.first() is None:
        users = [
            User(username='student_user', password=generate_password_hash('Student@123'), role='Student', phone='+1234567890', email='student@school.edu'),
            User(username='teacher_user', password=generate_password_hash('Teacher@123'), role='Teacher', phone='+1234567891', email='teacher@school.edu'),
            User(username='admin_user', password=generate_password_hash('Admin@123'), role='Administrator', phone='+1234567892', email='admin@school.edu')
        ]
        db.session.bulk_save_objects(users)
        db.session.commit()
