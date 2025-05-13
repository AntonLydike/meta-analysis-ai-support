from flask import Flask, render_template, g, request, redirect, url_for, abort
import sqlite3
import os
from webapp.db import get_connection

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), '../webapp.db')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    db = get_db()

    # Step 1: Get distinct reviewer names
    reviewers = [row['reviewer'] for row in db.execute("SELECT DISTINCT reviewer FROM reviews").fetchall()]

    # Step 2: Get the current page from the query parameter, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 1000  # Set how many publications per page

    # Step 3: Fetch the total number of publications to calculate total pages
    total_publications = db.execute("SELECT COUNT(*) FROM publications").fetchone()[0]
    total_pages = (total_publications + per_page - 1) // per_page  # Ceiling division

    # Step 4: Fetch a specific subset of publications for the current page
    offset = (page - 1) * per_page


    sort_by_reviewer = request.args.get('sort')
    sort_dir = ""
    if sort_by_reviewer is None:
        publications = db.execute(
            "SELECT p.id, p.title, p.year FROM publications as p ORDER BY year DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
    else:
        if sort_by_reviewer.startswith('-'):
            order = 'ASC'
            sort_dir = '▲'
            sort_by_reviewer = sort_by_reviewer[1:]
        else:
            sort_dir = '▼'
            order = 'DESC'
        publications = db.execute(
            f"SELECT p.id, p.title, p.year FROM publications as p LEFT JOIN reviews as r ON r.publication_id = p.id AND r.reviewer = ? ORDER BY r.rating {order}, p.year DESC LIMIT ? OFFSET ?",
            (sort_by_reviewer, per_page, offset)
        ).fetchall()

    # Step 5: Fetch all reviews
    reviews = db.execute("SELECT publication_id, reviewer, rating FROM reviews").fetchall()

    # Step 6: Build a lookup table: { (publication_id, reviewer) : [ratings] }
    review_lookup = {}
    for r in reviews:
        key = (r['publication_id'], r['reviewer'])
        review_lookup.setdefault(key, []).append(r['rating'])  # Keep as strings for display

    # Step 7: Build final rows for template
    rows = []
    for pub in publications:
        row = {
            'id': pub['id'],
            'title': pub['title'],
            'year': pub['year'],
        }
        for reviewer in reviewers:
            key = (pub['id'], reviewer)
            row[reviewer] = review_lookup.get(key, [])
        rows.append(row)

    # Step 8: Return the rendered template with pagination details
    return render_template(
        'index.html',
        publications=rows,
        reviewers=reviewers,
        page=page,
        total_pages=total_pages,
        sort_by=sort_by_reviewer,
        sort_dir=sort_dir
    )


@app.route('/publication/<int:pub_id>/review', methods=['POST'])
def add_review(pub_id):
    db = get_connection(DATABASE)

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

    rev = db.execute('SELECT id FROM reviews WHERE reviewer = ? and publication_id = ?', (reviewer, pub_id)).fetchall()
    if len(rev) > 0:
        # update it!
        print("updating")
        review_id = rev[0][0]
        db.execute('UPDATE reviews SET rating = ?, reason = ? WHERE id = ?', (rating, reason, review_id))
    else:
        # Insert into reviews
        print("inserting")
        db.execute(
            """
            INSERT INTO reviews (publication_id, rating, reviewer, reason, raw_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pub_id, rating, reviewer, reason, '{}')
        )
    db.commit()

    return redirect(url_for('publication', pub_id=pub_id))


@app.route('/publication/<int:pub_id>')
def publication(pub_id):
    db = get_db()

    publication = db.execute(
        "SELECT * FROM publications WHERE id = ?", (pub_id,)
    ).fetchone()

    reviews = db.execute(
        "SELECT * FROM reviews WHERE publication_id = ?", (pub_id,)
    ).fetchall()

    if not publication:
        return "Publication not found", 404

    return render_template("publication.html", publication=publication, reviews=reviews)