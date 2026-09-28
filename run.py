from flask import render_template
from app import create_app

app = create_app()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/index')
def index_alias():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/portal')
def portal_page():
    return render_template('authshield.html')

@app.route('/platform')
def platform_page():
    return render_template('platform.html')

@app.route('/solutions')
def solutions_page():
    return render_template('solutions.html')

@app.route('/resources')
def resources_page():
    return render_template('resources.html')

@app.route('/company')
def company_page():
    return render_template('company.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/calendar')
def calendar_page():
    return render_template('calendar.html')

if __name__ == '__main__':
    # threaded=True so concurrent requests (e.g. a concurrent brute-force
    # test) are actually handled in parallel instead of queued one at a
    # time; safe now that SQLite is in WAL mode with a busy_timeout set
    # (see app/__init__.py).
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)