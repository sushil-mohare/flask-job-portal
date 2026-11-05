# Job Portal Web Application

## Description
A full-stack web application built using Python (Flask) and PostgreSQL. This platform connects recruiters with job seekers. Recruiters can post jobs, and candidates can search for jobs and apply.

## Tech Stack
- **Frontend:** HTML5, CSS3
- **Backend:** Python (Flask)
- **Database:** PostgreSQL

## Key Features
- **Dual Authentication:** Separate login/signup for Candidates and Recruiters.
- **Recruiter Dashboard:** Create, update, and delete job postings.
- **Candidate Dashboard:** Search jobs by keyword/location and apply.
- **Database:** Fully relational PostgreSQL database with tables for Users, Jobs, and Applications.

## How to Run Locally
1. Clone the repository.
2. Create a virtual environment and activate it.
3. Install dependencies: `pip install -r requirements.txt`
4. Create a PostgreSQL database named `job_portal_db`.
5. Update the database URI in `app.py` with your local PostgreSQL credentials.
6. Run the application: `python app.py`

## Author
- **Sushil Mohare**
