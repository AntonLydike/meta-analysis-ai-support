import os
import sqlite3
import sys
from typing import TextIO
import rispy
import json
import time
import math
import csv

SCHEMA = """
CREATE TABLE publications (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    doi TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    year INTEGER,
    raw_data TEXT
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    reviewer TEXT,
    reason TEXT,
    raw_data TEXT,
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE
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
    return sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)


def read_bibliography_db(source: str):
    print("Loading bibliography...", file=sys.stderr)
    with open(source, 'r') as bibliography_file:
        entries = rispy.load(bibliography_file)
    conn = get_connection()
    cur = conn.cursor()
    t0 = time.time()
    for i, entry in enumerate(entries):
        cur.execute(
            'INSERT INTO publications(id, title, doi, authors, abstract, year, raw_data) VALUES (?,?,?,?,?,?,?)',
            (
                i, 
                entry.get('title', ''), 
                ensure_url(entry.get('doi', '')),
                ', '.join(entry.get('authors', [])),
                entry.get('abstract', ''), 
                int(entry.get('year', 0)), 
                json.dumps(entry),
            )
        )
        print_progress(i+1,len(entries), t0)
        # periodically commit
        if i % 500 == 0:
            conn.commit()
    conn.commit()

def ensure_url(doi: str) -> str:
    if doi == '':
        return doi
    if not doi.startswith('https://'):
        return "{}{}".format('https://dx.doi.org/', doi)
    return doi

def read_ratings(source: str):
    letters = "abcdefghijklmnopqrstuvwxyz"
    conn = get_connection()
    cur = conn.cursor()
    print(f"loading reviews '{source}'...")
    with open(source, 'r') as f:
        for i, line in enumerate(f):
            if not f:
                continue
            data = json.loads(line)
            cur.execute(
                'INSERT INTO reviews (publication_id, rating, reviewer, reason, raw_data) VALUES (?,?,?,?,?)',
                (
                    data['id'],
                    data['score'],
                    "{}-{}".format(data['model'], letters[data['attempt']]),
                    data['reason'],
                    line
                )
            )
            if i % 500 == 0:
                conn.commit()


def print_progress(current, total, start_time):
    percent = 100 * current // total
    elapsed = time.time() - start_time
    avg_time = elapsed / (current + 1)
    remaining = avg_time * (total - current - 1)

    bar_len = 50
    filled_len = int(bar_len * percent // 100)
    bar = '=' * filled_len + '-' * (bar_len - filled_len)
    size = math.ceil(math.log10(total))

    print(f'\r[{bar}] {percent}% ({current:0{size}}/{total}) - ETA: {remaining:.1f}s', flush=True, end="")
    if current == total:
        print()

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
    print(f"loading reviews '{file}'...")
    with open(file, 'r', newline='') as f:
        lines=line_count(f)
        reader = csv.reader(f)
        t0 = time.time()

        headers = next(reader)
        title = headers.index('Title')
        year = headers.index('Published Year')

        for i, line in enumerate(reader):
            if not f:
                continue

            pub = cur.execute('SELECT id FROM publications where title = ? and year = ?', (line[title], line[year])).fetchall()
            if len(pub) != 1:
                print("Error: multiple publications matching year={} {}".format(line[title], line[year]))
                raise ValueError("Error: multiple publications matching year={} {}".format(line[title], line[year]))
            pub_id = pub[0][0]

            cur.execute(
                'INSERT INTO reviews (publication_id, rating, reviewer, reason, raw_data) VALUES (?,?,?,?,?)',
                (
                    pub_id,
                    0,
                    'human',
                    '',
                    '{}',
                )
            )
            print_progress(i+1, lines, t0)
        print("fixing up relevant reviews.")
        cur.execute('''INSERT INTO reviews (publication_id, rating, reviewer, 'reason', 'raw_data')
SELECT p.id, 100, 'human', '', '{}'
FROM publications p
WHERE NOT EXISTS (
    SELECT 1
    FROM reviews r
    WHERE r.publication_id = p.id AND r.reviewer = 'human'
);''')
        conn.commit()

if __name__ == '__main__':
    import argparse
    args = argparse.ArgumentParser()
    args.add_argument('-c', '--create', help='Create database', action='store_true')
    args.add_argument('-b', '--bib', help='bibliography file', nargs='?')
    args.add_argument('-r','--reviews', help='review file (JSONL)', nargs='*')
    args.add_argument('--human-marked-irrelevant', help='CSV export of marked irrelevant papers', nargs='?')

    ns = args.parse_args()

    if ns.create:
        initialize_db()
    
    if ns.bib:
        read_bibliography_db(ns.bib)

    for review in (ns.reviews or []):
        read_ratings(review)
    
    if ns.human_marked_irrelevant:
        import_human_marked_irrelevant_cases(ns.human_marked_irrelevant)
