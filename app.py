from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, send_from_directory, Response
import psycopg2
import psycopg2.extras
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
import mimetypes

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

# File upload configuration
UPLOAD_FOLDER = 'static/uploads/resumes'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Register mime types
mimetypes.add_type('application/pdf', '.pdf')
mimetypes.add_type('application/msword', '.doc')
mimetypes.add_type('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx')

# ==================== PostgreSQL Configuration ====================
DB_CONFIG = {
    'host': 'localhost',
    'database': 'job_portal',
    'user': 'postgres',
    'password': 'root',
    'port': '5432'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    """Get PostgreSQL database connection."""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

def get_cursor(conn):
    """Get dictionary cursor for PostgreSQL."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    """Initialize the database with required tables."""
    conn = get_db()
    cur = get_cursor(conn)
    
    # Users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Jobseeker profiles
    cur.execute('''
        CREATE TABLE IF NOT EXISTS jobseekers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            full_name VARCHAR(150) NOT NULL,
            qualification TEXT,
            experience TEXT,
            skills TEXT,
            description TEXT,
            resume_filename TEXT,
            profile_pic TEXT
        )
    ''')
    
    # Employer profiles
    cur.execute('''
        CREATE TABLE IF NOT EXISTS employers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_name VARCHAR(200) NOT NULL,
            contact_person VARCHAR(150),
            industry VARCHAR(100),
            description TEXT,
            company_logo TEXT
        )
    ''')
    
    # Jobs
    cur.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            employer_id INTEGER NOT NULL REFERENCES employers(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            requirements TEXT,
            location VARCHAR(150),
            salary VARCHAR(100),
            job_type VARCHAR(50),
            category VARCHAR(100),
            expiry_date VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Applications
    cur.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            jobseeker_id INTEGER NOT NULL REFERENCES jobseekers(id) ON DELETE CASCADE,
            status VARCHAR(20) DEFAULT 'pending',
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, jobseeker_id)
        )
    ''')
    
    # Saved Jobs
    cur.execute('''
        CREATE TABLE IF NOT EXISTS saved_jobs (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            jobseeker_id INTEGER NOT NULL REFERENCES jobseekers(id) ON DELETE CASCADE,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, jobseeker_id)
        )
    ''')
    
    conn.commit()
    
    # Create default admin
    cur.execute("SELECT * FROM users WHERE role = 'admin'")
    admin = cur.fetchone()
    if not admin:
        hashed_pw = generate_password_hash('admin123')
        cur.execute("INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
                     ('admin', 'admin@jobportal.com', hashed_pw, 'admin'))
        conn.commit()
    
    cur.close()
    conn.close()

init_db()

# ==================== Helper Functions ====================
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def role_required(role):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if session.get('role') != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ==================== Routes ====================
@app.route('/')
def index():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT j.*, e.company_name 
        FROM jobs j
        JOIN employers e ON j.employer_id = e.id
        ORDER BY j.created_at DESC
        LIMIT 6
    ''')
    recent_jobs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', recent_jobs=recent_jobs)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        conn = get_db()
        cur = get_cursor(conn)
        
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        existing = cur.fetchone()
        if existing:
            flash('Username or email already exists.', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('register'))
        
        hashed_pw = generate_password_hash(password)
        cur.execute("INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s) RETURNING id",
                     (username, email, hashed_pw, role))
        user_id = cur.fetchone()['id']
        conn.commit()
        
        if role == 'jobseeker':
            cur.execute("INSERT INTO jobseekers (user_id, full_name) VALUES (%s, %s)", (user_id, username))
        elif role == 'employer':
            cur.execute("INSERT INTO employers (user_id, company_name) VALUES (%s, %s)", (user_id, username))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cur = get_cursor(conn)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session['role']
    user_id = session['user_id']
    conn = get_db()
    cur = get_cursor(conn)
    
    if role == 'jobseeker':
        cur.execute("SELECT * FROM jobseekers WHERE user_id = %s", (user_id,))
        profile = cur.fetchone()
        cur.execute('''
            SELECT a.*, j.title as job_title, j.location, e.company_name 
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN employers e ON j.employer_id = e.id
            WHERE a.jobseeker_id = %s
            ORDER BY a.applied_at DESC
            LIMIT 5
        ''', (profile['id'],))
        applications = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as count FROM saved_jobs WHERE jobseeker_id = %s", (profile['id'],))
        saved_count = cur.fetchone()['count']
        cur.close()
        conn.close()
        return render_template('jobseeker_dashboard.html', profile=profile, applications=applications, saved_count=saved_count)
    
    elif role == 'employer':
        cur.execute("SELECT * FROM employers WHERE user_id = %s", (user_id,))
        profile = cur.fetchone()
        if profile:
            cur.execute("SELECT * FROM jobs WHERE employer_id = %s ORDER BY created_at DESC", (profile['id'],))
            jobs = cur.fetchall()
        else:
            jobs = []
        cur.close()
        conn.close()
        return render_template('employer_dashboard.html', profile=profile, jobs=jobs)
    
    elif role == 'admin':
        cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('admin_dashboard.html', users=users)
    
    cur.close()
    conn.close()
    return render_template('dashboard.html')

# ==================== Jobseeker Routes ====================
@app.route('/jobseeker/profile', methods=['GET', 'POST'])
@login_required
@role_required('jobseeker')
def jobseeker_profile():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT * FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    profile = cur.fetchone()
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        qualification = request.form['qualification']
        experience = request.form['experience']
        skills = request.form['skills']
        description = request.form['description']
        
        cur.execute('''
            UPDATE jobseekers 
            SET full_name = %s, qualification = %s, experience = %s, skills = %s, description = %s
            WHERE user_id = %s
        ''', (full_name, qualification, experience, skills, description, session['user_id']))
        conn.commit()
        
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename:
                if allowed_file(file.filename):
                    try:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        original_filename = secure_filename(file.filename)
                        filename = f"{session['username']}_{timestamp}_{original_filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        
                        file.save(file_path)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                            cur.execute("UPDATE jobseekers SET resume_filename = %s WHERE user_id = %s", 
                                         (filename, session['user_id']))
                            conn.commit()
                            flash('Profile updated and resume uploaded successfully!', 'success')
                        else:
                            flash('File was not saved properly. Please try again.', 'danger')
                    except Exception as e:
                        flash(f'Error uploading file: {str(e)}', 'danger')
                else:
                    flash('Invalid file format. Please upload PDF, DOC, or DOCX.', 'danger')
            else:
                flash('Please select a file to upload.', 'warning')
        else:
            flash('Profile updated successfully!', 'success')
        
        cur.close()
        conn.close()
        return redirect(url_for('jobseeker_profile'))
    
    cur.close()
    conn.close()
    return render_template('jobseeker_profile.html', profile=profile)

@app.route('/view_resume/<int:seeker_id>')
@login_required
def view_resume(seeker_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT resume_filename FROM jobseekers WHERE id = %s", (seeker_id,))
    profile = cur.fetchone()
    cur.close()
    conn.close()
    
    if not profile or not profile['resume_filename']:
        flash('No resume uploaded.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
    
    filename = profile['resume_filename']
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(file_path):
        flash('Resume file not found.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
    
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        if len(file_data) == 0:
            flash('Resume file is empty.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        response = Response(file_data, content_type='application/pdf')
        response.headers['Content-Disposition'] = 'inline; filename="' + filename + '"'
        response.headers['Content-Length'] = len(file_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        
        return response
    except Exception as e:
        flash(f'Error opening resume: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/download_resume/<int:seeker_id>')
@login_required
def download_resume(seeker_id):
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT resume_filename FROM jobseekers WHERE id = %s", (seeker_id,))
    profile = cur.fetchone()
    cur.close()
    conn.close()
    
    if not profile or not profile['resume_filename']:
        flash('No resume uploaded for this candidate.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
    
    filename = profile['resume_filename']
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(file_path):
        flash('Resume file not found on server.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
    
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if ext == 'pdf':
            mimetype = 'application/pdf'
        elif ext == 'doc':
            mimetype = 'application/msword'
        elif ext == 'docx':
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            mimetype = 'application/octet-stream'
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        response = Response(file_data, content_type=mimetype)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = len(file_data)
        
        return response
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/jobs')
@login_required
@role_required('jobseeker')
def view_jobs():
    conn = get_db()
    cur = get_cursor(conn)
    
    category = request.args.get('category', '')
    job_type = request.args.get('job_type', '')
    location = request.args.get('location', '')
    
    query = '''
        SELECT j.*, e.company_name 
        FROM jobs j
        JOIN employers e ON j.employer_id = e.id
        WHERE 1=1
    '''
    params = []
    
    if category:
        query += " AND j.category = %s"
        params.append(category)
    if job_type:
        query += " AND j.job_type = %s"
        params.append(job_type)
    if location:
        query += " AND j.location ILIKE %s"
        params.append(f"%{location}%")
    
    query += " ORDER BY j.created_at DESC"
    
    cur.execute(query, params)
    jobs = cur.fetchall()
    
    cur.execute("SELECT id FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    seeker = cur.fetchone()
    
    applied_jobs = set()
    saved_jobs = set()
    
    if seeker:
        cur.execute("SELECT job_id FROM applications WHERE jobseeker_id = %s", (seeker['id'],))
        applied_jobs = {row['job_id'] for row in cur.fetchall()}
        
        cur.execute("SELECT job_id FROM saved_jobs WHERE jobseeker_id = %s", (seeker['id'],))
        saved_jobs = {row['job_id'] for row in cur.fetchall()}
    
    cur.execute("SELECT DISTINCT category FROM jobs WHERE category IS NOT NULL AND category != ''")
    categories = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('view_jobs.html', jobs=jobs, applied_jobs=applied_jobs, 
                         saved_jobs=saved_jobs, categories=categories, 
                         selected_category=category, selected_type=job_type, selected_location=location)

@app.route('/apply/<int:job_id>')
@login_required
@role_required('jobseeker')
def apply_job(job_id):
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()
    if not job:
        flash('Job not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('view_jobs'))
    
    cur.execute("SELECT id FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    seeker = cur.fetchone()
    if not seeker:
        flash('Please complete your profile first.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('jobseeker_profile'))
    
    cur.execute("SELECT id FROM applications WHERE job_id = %s AND jobseeker_id = %s", (job_id, seeker['id']))
    existing = cur.fetchone()
    if existing:
        flash('You have already applied for this job.', 'warning')
        cur.close()
        conn.close()
        return redirect(url_for('view_jobs'))
    
    cur.execute("INSERT INTO applications (job_id, jobseeker_id, status) VALUES (%s, %s, %s)",
                  (job_id, seeker['id'], 'pending'))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Application submitted successfully!', 'success')
    return redirect(url_for('view_jobs'))

@app.route('/save_job/<int:job_id>')
@login_required
@role_required('jobseeker')
def save_job(job_id):
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()
    if not job:
        flash('Job not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('view_jobs'))
    
    cur.execute("SELECT id FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    seeker = cur.fetchone()
    if not seeker:
        flash('Please complete your profile first.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('jobseeker_profile'))
    
    cur.execute("SELECT id FROM saved_jobs WHERE job_id = %s AND jobseeker_id = %s", (job_id, seeker['id']))
    existing = cur.fetchone()
    if existing:
        cur.execute("DELETE FROM saved_jobs WHERE id = %s", (existing['id'],))
        conn.commit()
        flash('Job removed from saved list.', 'info')
    else:
        cur.execute("INSERT INTO saved_jobs (job_id, jobseeker_id) VALUES (%s, %s)", (job_id, seeker['id']))
        conn.commit()
        flash('Job saved successfully!', 'success')
    
    cur.close()
    conn.close()
    return redirect(request.referrer or url_for('view_jobs'))

@app.route('/saved_jobs')
@login_required
@role_required('jobseeker')
def saved_jobs():
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    seeker = cur.fetchone()
    jobs = []
    applied_jobs = set()
    
    if seeker:
        cur.execute('''
            SELECT j.*, e.company_name, s.saved_at
            FROM saved_jobs s
            JOIN jobs j ON s.job_id = j.id
            JOIN employers e ON j.employer_id = e.id
            WHERE s.jobseeker_id = %s
            ORDER BY s.saved_at DESC
        ''', (seeker['id'],))
        jobs = cur.fetchall()
        
        cur.execute("SELECT job_id FROM applications WHERE jobseeker_id = %s", (seeker['id'],))
        applied_jobs = {row['job_id'] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    return render_template('saved_jobs.html', jobs=jobs, applied_jobs=applied_jobs)

@app.route('/track_jobs')
@login_required
@role_required('jobseeker')
def track_jobs():
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id FROM jobseekers WHERE user_id = %s", (session['user_id'],))
    seeker = cur.fetchone()
    applications = []
    
    if seeker:
        cur.execute('''
            SELECT a.*, j.title as job_title, j.location, e.company_name
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN employers e ON j.employer_id = e.id
            WHERE a.jobseeker_id = %s
            ORDER BY a.applied_at DESC
        ''', (seeker['id'],))
        applications = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('track_jobs.html', applications=applications)

# ==================== Employer Routes ====================
@app.route('/employer/profile', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def employer_profile():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT * FROM employers WHERE user_id = %s", (session['user_id'],))
    profile = cur.fetchone()
    
    if request.method == 'POST':
        company_name = request.form['company_name']
        contact_person = request.form['contact_person']
        industry = request.form['industry']
        description = request.form['description']
        
        cur.execute('''
            UPDATE employers 
            SET company_name = %s, contact_person = %s, industry = %s, description = %s
            WHERE user_id = %s
        ''', (company_name, contact_person, industry, description, session['user_id']))
        conn.commit()
        flash('Profile updated successfully!', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('employer_profile'))
    
    cur.close()
    conn.close()
    return render_template('employer_profile.html', profile=profile)

@app.route('/post_job', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def post_job():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        requirements = request.form['requirements']
        location = request.form['location']
        salary = request.form['salary']
        job_type = request.form['job_type']
        category = request.form.get('category', '')
        expiry_date = request.form.get('expiry_date', '')
        
        conn = get_db()
        cur = get_cursor(conn)
        
        cur.execute("SELECT id FROM employers WHERE user_id = %s", (session['user_id'],))
        employer = cur.fetchone()
        if employer:
            cur.execute('''
                INSERT INTO jobs (employer_id, title, description, requirements, location, salary, job_type, category, expiry_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (employer['id'], title, description, requirements, location, salary, job_type, category, expiry_date))
            conn.commit()
            flash('Job posted successfully!', 'success')
        else:
            flash('Please complete your employer profile first.', 'danger')
        
        cur.close()
        conn.close()
        return redirect(url_for('dashboard'))
    
    return render_template('post_job.html')

@app.route('/delete_job/<int:job_id>')
@login_required
@role_required('employer')
def delete_job(job_id):
    conn = get_db()
    cur = get_cursor(conn)
    
    # Verify this job belongs to this employer
    cur.execute('''
        SELECT j.id FROM jobs j
        JOIN employers e ON j.employer_id = e.id
        WHERE j.id = %s AND e.user_id = %s
    ''', (job_id, session['user_id']))
    job = cur.fetchone()
    
    if not job:
        flash('Job not found or you do not have permission to delete it.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('dashboard'))
    
    cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Job deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/view_candidates')
@login_required
@role_required('employer')
def view_candidates():
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id FROM employers WHERE user_id = %s", (session['user_id'],))
    employer = cur.fetchone()
    
    if not employer:
        flash('Please complete your employer profile first.', 'warning')
        cur.close()
        conn.close()
        return redirect(url_for('employer_profile'))
    
    cur.execute("SELECT id, title FROM jobs WHERE employer_id = %s ORDER BY created_at DESC", (employer['id'],))
    jobs = cur.fetchall()
    
    candidates = []
    selected_job_id = request.args.get('job_id')
    
    if selected_job_id:
        cur.execute('''
            SELECT a.id as application_id, a.status, a.applied_at,
                   j.title as job_title,
                   js.id as seeker_id, js.full_name, js.qualification, js.experience, js.skills, js.description, js.resume_filename
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN jobseekers js ON a.jobseeker_id = js.id
            WHERE j.employer_id = %s AND j.id = %s
            ORDER BY a.applied_at DESC
        ''', (employer['id'], selected_job_id))
        candidates = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('view_candidates.html', jobs=jobs, candidates=candidates, selected_job_id=selected_job_id)

@app.route('/update_application_status/<int:application_id>', methods=['POST'])
@login_required
@role_required('employer')
def update_application_status(application_id):
    new_status = request.form['status']
    
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute('''
        SELECT a.*, js.full_name, js.user_id, u.email, j.title, e.company_name, j.id as job_id
        FROM applications a
        JOIN jobseekers js ON a.jobseeker_id = js.id
        JOIN users u ON js.user_id = u.id
        JOIN jobs j ON a.job_id = j.id
        JOIN employers e ON j.employer_id = e.id
        WHERE a.id = %s
    ''', (application_id,))
    application = cur.fetchone()
    
    if not application:
        flash('Application not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('view_candidates'))
    
    cur.execute("UPDATE applications SET status = %s WHERE id = %s", (new_status, application_id))
    conn.commit()
    
    if new_status == 'shortlisted':
        flash(f'Application status updated to "Shortlisted". Notification would be sent to {application["email"]}', 'success')
    elif new_status == 'rejected':
        flash(f'Application status updated to "Rejected". Notification would be sent to {application["email"]}', 'info')
    elif new_status == 'hired':
        flash(f'Congratulations! {application["full_name"]} has been hired for {application["title"]}.', 'success')
    else:
        flash(f'Application status updated to "{new_status}".', 'info')
    
    cur.close()
    conn.close()
    return redirect(url_for('view_candidates', job_id=application['job_id']))

# ==================== Admin Routes ====================
@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    conn = get_db()
    cur = get_cursor(conn)
    
    if user_id == session['user_id']:
        flash('You cannot delete your own admin account.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('admin_users'))
    
    cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        flash('User not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('admin_users'))
    
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    conn = get_db()
    cur = get_cursor(conn)
    
    cur.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        flash('User not found.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('admin_users'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        role = request.form['role']
        
        cur.execute(
            "SELECT id FROM users WHERE (username = %s OR email = %s) AND id != %s", 
            (username, email, user_id)
        )
        existing = cur.fetchone()
        
        if existing:
            flash('Username or email already exists.', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('admin_edit_user', user_id=user_id))
        
        cur.execute("UPDATE users SET username = %s, email = %s, role = %s WHERE id = %s", 
                      (username, email, role, user_id))
        conn.commit()
        flash('User updated successfully.', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('admin_users'))
    
    cur.close()
    conn.close()
    return render_template('admin_edit_user.html', user=user)

if __name__ == '__main__':
    app.run(debug=True)