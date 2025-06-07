import sqlite3
import sys
import json
import time
import uuid
from aalib.progress import progress
from aalib.colors import FMT
from aalib.multilines import MultilineCtx

from webapp.db import get_connection
PROMPT = """
You are an experienced researcher performing a meta-analysis on how romantic relationships impact happiness.

Your task is to assess an abstract and to identify if it is suitable for inclusion into this meta-analysis.

Criteria for inclusion:
- Participants must be human adults (mean age >=18 and min. age >= 16).
- The study must include measures of romantic relationship status (e.g., single, partnered, dating) and subjective well-being (e.g., life satisfaction, positive or negative affect) at the individual level, and report the association between them.
- Studies must contain at least two distinct romantic relationship categories in order to assess differences in subjective well-being across relationship status.
- Studies must report sufficient statistical information to allow for effect size calculation, such as correlation coefficients (r), group means and standard deviations, sample sizes, or other convertible statistics (e.g., t-values, F-values, χ² values, or standardized beta coefficients).
- Publications written in English.
- Full-text articles available.
- Empirical studies with quantitative designs, including cross-sectional, observational, or correlational methods.
- Studies that use validated scales to measure subjective well-being (e.g., life satisfaction, positive affect, negative affect).
- Studies must measure subjective well-being as a trait-level construct (e.g., general life satisfaction or typical affect), rather than state-level or momentary well-being (e.g., daily diary designs).
- In the case of multiple publications from the same dataset, only the most relevant or comprehensive will be retained.

Criteria for exclusion:
- Studies that did not report sample size and effect size metrics (e.g., correlation coefficients or other statistics convertible to effect sizes, such as β-values, t-values, etc.).
- Articles published in languages other than English.
- Studies for which full-text was not available.
- Non-empirical or qualitative studies, including systematic reviews, scoping reviews, meta-analyses, and bibliometric analyses.
- Grey literature, such as unpublished reports, dissertations, and theses.
- Studies measure subjective well-being at the state-level or momentary well-being (e.g., daily diary designs).

**Title:**
{title}

**Abstract:**
{abstract}


Please provide a written summary, followed by a JSON response containing a rating of relevancy for the work as well as a description. The JSON schema should be `{{"score": Number, "reason": String}}`, where score is between 0 and 100.
"""

def make_job(db: sqlite3.Connection, i: int, model: str, num_completed: int):
    id = str(uuid.uuid4())
    db.execute(
        'INSERT INTO jobs (id, name, model, prompt, repeats, status, time_created, time_started, time_taken, num_completed) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (
            id,
            f'i{i}:{model}',
            model,
            PROMPT,
            2,
            'FINISHED',
            time.time(),
            time.time(),
            100,
            num_completed,
        )
    )
    return id


if __name__ == '__main__':
    files = sys.argv[1:]
    db = get_connection()

    ctx = MultilineCtx(2)
    for i, file in enumerate(progress(files, color=FMT.BLUE, file=ctx.ostream_for(1))):
        with open(file, 'r') as f:
            line = f.readline()
            f.seek(0)
            model = json.loads(line)['model']
            lines = f.read().count('\n')
            job = make_job(db, i, model, lines)
            f.seek(0)

            for line in progress(f, count=lines, color=FMT.GREEN, file=ctx.ostream_for(0), message=file):
                data = json.loads(line)
                db.execute('INSERT INTO reviews (publication_id, job_id, created, rating, reason, raw_data) VALUES (?,?,?,?,?,?)', (
                    data['id'],
                    job,
                    time.time(),
                    data['score'],
                    data['reason'],
                    line,
                ))
        db.commit()






