from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
import uuid
import csv
import json
import rispy
import traceback

from dataclasses import dataclass

from webapp.db import get_connection

@dataclass
class Export:
    uuid: str
    job_id: str
    comparison: str
    rating: str
    format: str
    total: int = 1
    processed: int = 0
    done: bool = False

    def file_name(self):
        return f'out/{self.uuid}.{self.format}'

class Exporter:
    def __init__(self, num_threads: int):
        self.pool = ThreadPoolExecutor(num_threads)
        self.by_job = defaultdict(list)
        self.by_id = dict()
        self.outdir = 'out/'

        # load jobs from database
        conn = get_connection()
        for row in conn.execute('SELECT * FROM exports'):
            exp = Export(row['id'], row['job_id'], row['comparison'], row['rating'], row['format'], 1, 1, True)
            self.by_id[exp.uuid] = exp
            self.by_job[exp.job_id].append(exp)


    def get_files_for_job(self, job_id: str) -> list[Export]:
        return self.by_job[job_id]

    def submit(self, job_id: str, comparison: Literal['ge', 'gt', 'le', 'lt'], rating: int, format: Literal['csv', 'ris']) -> Export:
        cmp = {'ge': '>=', 'le': '<=', 'lt': '<', 'gt': '>'}.get(comparison, None)
        if cmp is None:
            raise ValueError(cmp)
        
        exp = Export(
            uuid=str(uuid.uuid4()),
            job_id=job_id,
            comparison=cmp,
            rating=rating,
            format=format,
        )
        self.by_job[job_id].append(exp)
        self.by_id[exp.uuid] = exp

        self.pool.submit(_run_export, exp)

        return exp
    
    def get(self, uuid: str) -> Export | None:
        return self.by_id.get(uuid, None)

def _run_export(export: Export):
    try:
        conn = get_connection()

        cmp = export.comparison
        rating = export.rating
        job_id = export.job_id

        export.total = conn.execute(f'SELECT COUNT(*) FROM reviews WHERE job_id = ? AND rating {cmp} ?', (job_id, rating)).fetchone()[0]

        print(f'set export total to {export.total}')

        with open(export.file_name(), 'w') as f:
            if export.format == 'csv':
                # export csv
                data = conn.execute(f'SELECT "https://domain.com/publication/" || p.id as url, p.ext_id as id, p.title as title, p.doi as doi, p.authors as authors, p.abstract as abstract, p.year as year, p.human_score as human_score, p.human_reason as human_reason, r.rating as model_rating, r.reason as model_reason FROM publications AS p RIGHT JOIN reviews as R ON p.id = r.publication_id AND r.job_id = ? WHERE r.rating {cmp} ?', (job_id, rating))
                w = csv.writer(f)
                w.writerow(['url', 'id', 'title', 'doi', 'authors', 'abstract', 'year', 'human_score', 'human_reason', 'model_score', 'model_reason'])

                while True:
                    rows = data.fetchmany(1024)
                    if not rows:
                        break
                    w.writerows(rows)
                    export.processed += len(rows)

            elif export.format == 'ris':
                    # export ris
                    data = conn.execute(f'SELECT p.raw_data FROM publications AS p JOIN reviews as r ON p.id = r.publication_id AND r.job_id = ? WHERE r.rating {cmp} ?', (job_id, rating))

                    while True:
                        chunk = data.fetchmany(1024)
                        if not chunk:
                            break
                        try:
                            rispy.dump([json.loads(row[0]) for row in chunk], f)
                        except Exception as e:
                            print("error:")
                            print(e)
                        export.processed += len(chunk)

            else:
                raise ValueError("Unsupported export format", export.format)
        print("Export complete")
        export.done = True
        # write to db
        conn.execute('INSERT INTO exports (id, job_id, rating, comparison, format) VALUES (?,?,?,?,?)', (export.uuid, job_id, rating, cmp, export.format))
        conn.commit()

    except Exception as ex:
        print(ex)
        traceback.print_exc(ex)
        traceback.print_tb()


EXPORTER = Exporter(8)
