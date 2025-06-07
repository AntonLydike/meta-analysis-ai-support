import os
import sqlite3
import sys
from typing import TextIO
import rispy
import json
import csv
from aalib.progress import progress
from aalib.colors import FMT

SCHEMA = """
CREATE TABLE publications (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    doi TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    year INTEGER,
    raw_data TEXT,
    human_score INT,
    human_reason TEXT
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    repeats INTEGER NOT NULL,
    status TEXT NOT NULL,
    time_created INTEGER NOT NULL,
    time_started INTEGER NOT NULL,
    time_taken REAL NOT NULL,
    num_completed INTEGER NOT NULL
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    created INTEGER NOT NULL,
    rating REAL NOT NULL,
    reason TEXT,
    raw_data TEXT,
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES runs(id) ON DELETE CASCADE
);
"""

def initialize_db(db_path: str = 'webapp.db'):
    if os.path.exists(db_path):
        raise RuntimeError("Cannot create db: already exists")
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL;')  # Enable WAL mode
    conn.execute('PRAGMA synchronous=NORMAL;')  # Optional: improves write performance
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def get_connection(db_path: str = 'webapp.db') -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')  # Enable WAL mode
    conn.execute('PRAGMA synchronous=NORMAL;')  # Optional: improves write performance
    conn.commit()
    return conn


def read_bibliography_db(source: str):
    print("Loading bibliography...", file=sys.stderr)
    if source.endswith('.json') or source.endswith('.jsonl'):
        with open(source, 'r') as f:
            entries = [
                json.loads(line) for line in f
            ]
    else:
        with open(source, 'r') as bibliography_file:
            entries = rispy.load(bibliography_file)

    conn = get_connection()
    cur = conn.cursor()

    for i, entry in progress(enumerate(entries), count=len(entries)):
        cur.execute(
            'INSERT INTO publications(id, title, doi, authors, abstract, year, raw_data, human_score, human_reason) VALUES (?,?,?,?,?,?,?,?,?)',
            (
                i,
                entry.get('title', ''), 
                ensure_url(entry.get('doi', '')),
                ', '.join(entry.get('authors', [])),
                entry.get('abstract', ''), 
                int(entry.get('year', 0)), 
                json.dumps(entry),
                -1,
                "",
            )
        )
    conn.commit()

def ensure_url(doi: str) -> str:
    if doi == '':
        return doi
    if not doi.startswith('https://'):
        return "{}{}".format('https://dx.doi.org/', doi)
    return doi

def line_count(f: TextIO) -> int:
    p = f.tell()
    count = 0
    while (chunk := f.read(1024 * 1024)):
        count += chunk.count('\n')
    f.seek(p)
    return count

def import_human_marked_irrelevant_cases(file: str):
    conn = get_connection()
    cur = conn.cursor()
    print(f"loading human reviews '{file}'...")
    with open(file, 'r', newline='') as f:
        lines=line_count(f)
        reader = csv.reader(f)

        headers = next(reader)
        title = headers.index('Title')
        year = headers.index('Published Year')

        for i, line in progress(enumerate(reader), count=lines):
            if not f:
                continue

            pub = cur.execute('SELECT id FROM publications where title = ? and year = ?', (line[title], line[year])).fetchall()
            if len(pub) != 1:
                print("Error: multiple publications matching year={} {}".format(line[title], line[year]))
                raise ValueError("Error: multiple publications matching year={} {}".format(line[title], line[year]))
            pub_id = pub[0][0]

            cur.execute(
                'UPDATE publications SET human_score = ? WHERE id = ?',
                (0, pub_id)
            )

        print("fixing up relevant reviews.")
        cur.execute('UPDATE publications SET human_score = 100 WHERE human_score < 0')
        conn.commit()


def items_left_in_job(job_id: str, count: int):
    conn = get_connection()
    query = """SELECT p.*, ? - COALESCE(COUNT(r.id), 0) as num 
FROM publications as p 
LEFT JOIN reviews as r ON p.id = r.publication_id AND r.job_id = ? 
GROUP BY p.id 
ORDER BY p.human_score DESC 
HAVING num > 0"""
    for row in conn.execute(query, (count, job_id)):
        for _ in range(row['num']):
            yield row

def remaining_items_count(job_id: str, job_k : int | None = None):
    conn = get_connection()

    if job_k is None:
        job_k = conn.execute('SELECT repeats FROM jobs WHERE id = ?', (job_id,)).fetchone()[0]
    return conn.execute(
        "SELECT SUM(num) FROM ("
        "SELECT p.*, ? - COALESCE(COUNT(r.id), 0) as num "
        "FROM publications as p "
        "LEFT JOIN reviews as r ON p.id = r.publication_id AND r.job_id = ? "
        "GROUP BY p.id "
        "HAVING num > 0)", 
        (job_k, job_id)
    ).fetchone()[0]


if __name__ == '__main__':
    import argparse
    args = argparse.ArgumentParser()
    args.add_argument('-c', '--create', help='Create database', action='store_true')
    args.add_argument('-b', '--bib', help='bibliography file (JSON or txt)', nargs='?')
    args.add_argument('--human-marked-irrelevant', help='CSV export of marked irrelevant papers', nargs='?')

    ns = args.parse_args()

    if ns.create:
        initialize_db()
    
    if ns.bib:
        read_bibliography_db(ns.bib)

    if ns.human_marked_irrelevant:
        import_human_marked_irrelevant_cases(ns.human_marked_irrelevant)
