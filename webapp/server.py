from flask import Flask, render_template, g, request, redirect, url_for, abort, flash
from datetime import datetime
import sqlite3
import uuid
import time
import os

from markupsafe import Markup
from webapp.db import get_connection
from webapp.plot import render_heatmap
from aalib.duration import duration


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET")

if app.secret_key is not None:
    print("SECRETSSSS")


STATS_QUERY = """
WITH human_labels AS (
    SELECT id as publication_id,
            CASE WHEN human_score > ? THEN 1 ELSE 0 END AS is_relevant
    FROM publications
),
model_reviews AS (
    SELECT 
        jobs.model AS model_name,
        jobs.name as job_name,
        jobs.id as job_id,
        publication_id,
        CASE WHEN rating > ? THEN 1 ELSE 0 END AS predicted_relevant
    FROM reviews JOIN jobs ON reviews.job_id = jobs.id
),
joined AS (
    SELECT m.model_name, h.is_relevant, m.predicted_relevant, job_name, job_id
    FROM model_reviews m
    JOIN human_labels h ON m.publication_id = h.publication_id
),
aggregated AS (
    SELECT
        job_id,
        job_name,
        model_name,
        SUM(CASE WHEN is_relevant = 1 THEN 1 ELSE 0 END) AS relevant_papers,
        SUM(CASE WHEN is_relevant = 0 THEN 1 ELSE 0 END) AS irrelevant_papers,
        SUM(CASE WHEN predicted_relevant = 1 AND is_relevant = 1 THEN 1 ELSE 0 END) AS true_positives,
        SUM(CASE WHEN predicted_relevant = 1 AND is_relevant = 0 THEN 1 ELSE 0 END) AS false_positives,
        SUM(CASE WHEN predicted_relevant = 0 AND is_relevant = 1 THEN 1 ELSE 0 END) AS false_negatives,
        SUM(CASE WHEN predicted_relevant = 0 AND is_relevant = 0 THEN 1 ELSE 0 END) AS true_negatives
    FROM joined
    GROUP BY job_name
)
SELECT
    job_id,
    job_name,
    model_name,
    relevant_papers,
    irrelevant_papers,
    true_positives,
    false_positives,
    false_negatives,
    true_negatives,
    ROUND(1.0 * true_positives / NULLIF(true_positives + false_negatives, 0), 3) AS sensitivity,
    ROUND(1.0 * true_negatives / NULLIF(true_negatives + false_positives, 0), 3) AS specificity
FROM aggregated
ORDER BY model_name;
"""


def get_available_models():
    return (
        'llama3.1:8b', 
        'llama3.2:3b', 
        'gemma3:4b', 
        'deepseek-r1:1.5b',
        'qwen3:8b',
        'deepseek-r1:8b',
        )

@app.context_processor
def inject_globals():
    return {
        'current_year': datetime.now().year,
        'available_models': get_available_models(),
        'job_in_progress': job_in_progress(),
        'nav': [
            {
                "url": '/',
                "text": "Publications",
                "icon": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-book-half" viewBox="0 0 16 16"><path d="M8.5 2.687c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492zM8 1.783C7.015.936 5.587.81 4.287.94c-1.514.153-3.042.672-3.994 1.105A.5.5 0 0 0 0 2.5v11a.5.5 0 0 0 .707.455c.882-.4 2.303-.881 3.68-1.02 1.409-.142 2.59.087 3.223.877a.5.5 0 0 0 .78 0c.633-.79 1.814-1.019 3.222-.877 1.378.139 2.8.62 3.681 1.02A.5.5 0 0 0 16 13.5v-11a.5.5 0 0 0-.293-.455c-.952-.433-2.48-.952-3.994-1.105C10.413.809 8.985.936 8 1.783"/></svg>'
            },
            {
                "url": '/stats',
                "text": "Stats",
                "icon": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-bar-chart-line-fill" viewBox="0 0 16 16"><path d="M11 2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v12h.5a.5.5 0 0 1 0 1H.5a.5.5 0 0 1 0-1H1v-3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3h1V7a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v7h1z"/></svg>'
            },
            {
                "url": '/jobs',
                "text": "Jobs",
                "icon": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stack" viewBox="0 0 16 16"><path d="m14.12 10.163 1.715.858c.22.11.22.424 0 .534L8.267 15.34a.6.6 0 0 1-.534 0L.165 11.555a.299.299 0 0 1 0-.534l1.716-.858 5.317 2.659c.505.252 1.1.252 1.604 0l5.317-2.66zM7.733.063a.6.6 0 0 1 .534 0l7.568 3.784a.3.3 0 0 1 0 .535L8.267 8.165a.6.6 0 0 1-.534 0L.165 4.382a.299.299 0 0 1 0-.535z"/><path d="m14.12 6.576 1.715.858c.22.11.22.424 0 .534l-7.568 3.784a.6.6 0 0 1-.534 0L.165 7.968a.299.299 0 0 1 0-.534l1.716-.858 5.317 2.659c.505.252 1.1.252 1.604 0z"/></svg>'
            },
        ],
    }

def job_in_progress():
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM publications').fetchone()[0]
    if res := conn.execute("SELECT * FROM jobs WHERE status = 'RUNNING'").fetchone():
        return {
            **res,
            'eta': (res['time_taken'] / res['num_completed']) * (res['repeats'] * count - res['num_completed'])
        }

# register duration as a template filter:
app.template_filter('duration')(duration)

@app.template_filter()
def dt(t: float | int):
    t = datetime.fromtimestamp(t).astimezone().isoformat()
    return Markup(f'<time datetime="{t}">{t}</time>')

@app.route('/')
def index():
    db = get_connection()

    return render_template(
        'index.html',
        publications=db.execute('SELECT * FROM publications').fetchall(),
    )


@app.route('/publication/<int:pub_id>/review', methods=['POST'])
def add_review(pub_id):
    db = get_connection()

    # Validate that the publication exists
    pub = db.execute("SELECT id FROM publications WHERE id = ?", (pub_id,)).fetchone()
    if not pub:
        abort(404, description="Publication not found")

    # Extract form data
    reviewer = 'human' #request.form.get("reviewer")
    rating = request.form.get("rating")
    reason = request.form.get("reason")

    # Validate rating is an integer between 0 and 100
    try:
        rating = int(rating)
        assert 0 <= rating <= 100
    except (ValueError, AssertionError):
        abort(400, description="Rating must be an integer between 0 and 100")

    # Validate reviewer
    try:
        assert reviewer == 'human'
    except (ValueError, AssertionError):
        abort(400, description="Cannot submit non-human reviews")

    db.execute("UPDATE publications SET human_score = ?, human_reason = ? WHERE id = ?", (
        rating,
        reason,
        pub_id,
    ))

    return redirect(url_for('publication', pub_id=pub_id))


@app.route('/publication/<int:pub_id>')
def publication(pub_id):
    db = get_connection()

    publication = db.execute(
        "SELECT * FROM publications WHERE id = ?", (pub_id,)
    ).fetchone()

    reviews = db.execute(
        "SELECT r.id, r.job_id, r.created, r.rating, r.reason, j.name, j.model FROM reviews AS r JOIN jobs as j ON r.job_id = j.id WHERE r.publication_id = ?", (pub_id,)
    ).fetchall()

    if not publication:
        return "Publication not found", 404

    return render_template("publication.html", publication=publication, reviews=reviews)

@app.route('/stats')
def stats():
    db = get_connection()

    thresholds = [0, 20, 50]

    u_thresh = request.args.get('threshold', -1, type=int)
    if u_thresh != -1:
        thresholds.insert(0, u_thresh)
    tables = []

    sensitivity_map=[]
    specificity_map=[]
    jobs = []

    for threshold in thresholds:
        rows = db.execute(STATS_QUERY, (threshold, threshold)).fetchall()
        tables.append({
            'threshold': threshold,
            'rows': rows
        })
        sensitivity_map.append(tuple(
            row['sensitivity'] for row in rows
        ))
        specificity_map.append(tuple(
            row['specificity'] for row in rows
        ))
        jobs = tuple(
            row['job_name'] for row in rows
        )
    
    sens, spec = [render_heatmap(data, jobs, thresholds, title) for data, title in [(sensitivity_map, 'Sensitivity'),(specificity_map, 'Specificity')]]

    return render_template('model_comparison.html', 
                           tables=tables,
                           thresholds=thresholds,
                           sensitivity_svg=sens,
                           specificity_svg=spec
                           )


@app.route('/create_job', methods=['POST'])
def create_job():
    name = request.form.get('name', '').strip()
    model = request.form.get('model', '').strip()
    prompt = request.form.get('prompt', '').strip()
    repeats = request.form.get('repeats', '').strip()

    if not all([name, model, prompt, repeats]):
        flash("All fields are required.", "danger")
        return redirect(url_for('index'))

    try:
        repeats = int(repeats)
        if repeats < 1:
            raise ValueError
    except ValueError:
        flash("Repeats must be a positive integer.", "danger")
        return redirect(url_for('index'))

    if model not in get_available_models():
        flash("Invalid model selected.", "danger")
        return redirect(url_for('index'))

    conn = get_connection()
    try:
        existing = conn.execute("SELECT 1 FROM jobs WHERE name = ?", (name,)).fetchone()
        if existing:
            flash("A job with that name already exists.", "danger")
            return redirect(url_for('index'))

        job_id = str(uuid.uuid4())
        now = time.time()
        conn.execute("""
            INSERT INTO jobs (id, name, model, prompt, repeats, status, time_created, time_started, time_taken, num_completed)
            VALUES (?, ?, ?, ?, ?, 'WAITING', ?, 0, 0.0, '0')
        """, (job_id, name, model, prompt, repeats, now))
        conn.commit()
        flash("Job created successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error creating job: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('job_detail', job_id=job_id))

@app.route('/job/<job_id>')
def job_detail(job_id):
    conn = get_connection()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)

    status = request.args.get('status', None)
    if status is not None:
        if status not in ('WAITING', 'PAUSED'):
            flash(f'Invalid Status "{status}"', 'danger')
        else:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            return redirect(url_for('job_detail', job_id=job_id))

    total_items = job['repeats'] * conn.execute('SELECT COUNT(*) FROM publications').fetchone()[0]
    completed = int(job['num_completed'])
    progress = (completed / total_items * 100) if total_items else 0
    seconds_per_item = (job['time_taken'] / completed) if completed else 0
    estimated_remaining = (total_items - completed) * seconds_per_item if completed else None

    return render_template(
        "job_detail.html",
        job=job,
        total_items=total_items,
        completed=completed,
        progress=progress,
        seconds_per_item=seconds_per_item,
        estimated_remaining=estimated_remaining,
        reviews=conn.execute("SELECT p.id, p.title, p.year, p.human_score, r.rating as score, r.id as review_id FROM publications as p JOIN reviews as r ON r.publication_id = p.id WHERE job_id = ?", (job_id,)).fetchall()
    )

@app.route('/jobs')
def jobs():
    conn = get_connection()
    return render_template(
        'jobs.html',
        item_count=conn.execute('SELECT COUNT(*) FROM publications').fetchone()[0],
        jobs=conn.execute("SELECT * FROM jobs ORDER BY time_created DESC").fetchall()
    )