import ollama
import argparse
import rispy
import json
import re
import time
import sys
import math
from enum import Flag, auto

COLOR_SUPPORT = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

class FMT(Flag):
    RED = auto()
    BLUE = auto()
    YELLOW = auto()
    GREEN = auto()
    ORANGE = auto()
    BOLD = auto()
    GRAY = auto()
    UNDERLINE = auto()
    RESET = auto()

    def __str__(self) -> str:
        if not COLOR_SUPPORT:
            return ""
        fmt_str: list[str] = []

        if FMT.RED in self:
            fmt_str.append("\033[31m")
        if FMT.ORANGE in self:
            fmt_str.append("\033[33m")
        if FMT.GRAY in self:
            fmt_str.append("\033[37m")
        if FMT.GREEN in self:
            fmt_str.append("\033[32m")
        if FMT.BLUE in self:
            fmt_str.append("\033[34m")
        if FMT.YELLOW in self:
            fmt_str.append("\033[93m")
        if FMT.BOLD in self:
            fmt_str.append("\033[1m")
        if FMT.RESET in self:
            fmt_str.append("\033[0m")
        if FMT.UNDERLINE in self:
            fmt_str.append("\033[4m")

        return "".join(fmt_str)


WARN = FMT.ORANGE | FMT.UNDERLINE
ERR = FMT.RED | FMT.BOLD

MODELS = ('gemma3:12b', 'deepseek-r1:14b', 'llama3.1:8b', 'llama3.2:3b', 'gemma3:4b', 'qwen3:8b')

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

JSON_REGEX = re.compile(r'```(json)?\n(\{.*\})\n```', flags=re.DOTALL)


def classify_work(chat: ollama.Client,model: str, work: dict, stream_stdout: bool = False) -> dict | None:
    res = chat.generate(
        model=model, 
        prompt=PROMPT.format(title=work['title'], abstract=work['abstract']),
        stream=stream_stdout
    )
    if stream_stdout:
        print(f"============= {work['title']}")
        chunks = []
        for chunk in res:
            print(chunk['response'], end='', flush=True)
            chunks.append(chunk['response'])
        print()
        text = "".join(chunks)
    else:
        text = res['response']
    
    # read JSON from response
    data = extract_json(text)
    if data is None:
        print(f"\n{ERR}JSON error{FMT.RESET}", file=sys.stderr, flush=True)
        # try to rescure the JSON from the response body
        new_text = chat.generate(
            model='llama3.1:8b',
            prompt=f"Please extract the JSON from the following response body, make sure it's properly enclosed in three backticks and a json tag. Leave an empty response if no JSON can be found.\n\n---\n{text}"
        )['response']
        data = extract_json(new_text)
        # fail if second extraction did not work
        if data is None:
            return None
    
    if 'score' not in data or 'reason' not in data:
        return None
    
    data['full_text'] = text
    return data



def extract_json(text: str) -> dict | None:
    if (match := JSON_REGEX.search(text)) is None:
        return None
    try:
        res = json.loads(match.group(2))
        if not isinstance(res, dict):
            return None
        return res
    except json.JSONDecodeError:
        return None



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

if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('-i', '--input', help='input file name')
    args.add_argument('-o', '--output', help='output file name (- for stdout, which is the default)', default='-')
    args.add_argument('-c', '--count', help="number of works to classify (-1 means all)", default=-1, type=int)
    args.add_argument('-k', '--classification-attempts', help="Number of times to re-classify the same work", default=1, type=int)
    args.add_argument('-m', '--model', help='The model to use', choices=MODELS)
    args.add_argument('--stream', help='stream the model output as it generates', default=False, action='store_true')
    args.add_argument('--ollama-host', help='set ollama host', default='http://10.100.0.2:11434')

    ns = args.parse_args()

    print("Loading bibliography...")
    filepath = ns.input
    with open(filepath, 'r') as bibliography_file:
        entries = rispy.load(bibliography_file)
    
    print("Connecting to ollama...")
    client = ollama.Client(
        host=ns.ollama_host
    )

    if ns.output == '-':
        f = sys.stdout
        start = 0
    else:
        print("Checking output file for resume count...")
        f = open(ns.output, 'a+')
    
        # check progress made previously:
        f.seek(0)
        start = 0
        line = None
        for l in f:
            if l:
                line = l
        if line is not None:
            start = json.loads(line)['id']+1
        if start != 0:
            print(f"Resuming from idx {start}...")

    # calculate start/end coordinates in entries dict
    end = -1
    if ns.count != -1:
        end = start + ns.count

    runs = len(entries[start:end]) * ns.classification_attempts
    start_time = time.time()

    # classify data:
    for i, entry in enumerate(entries[start:end]):
        if 'abstract' not in entry or 'title' not in entry:
            print(f"\n{ERR}unable to classify {i+start}: missing abstract or title{FMT.RESET}", file=sys.stderr)
            continue
        for attempt in range(ns.classification_attempts):
            res = classify_work(client, ns.model, entry, ns.stream)
            if res is None:
                print(f"\n{ERR}unable to classify {i+start}: {entry['title']}{FMT.RESET}", file=sys.stderr)
                continue
            res['id'] = i+start
            res['model'] = ns.model
            res['attempt'] = attempt
            print(json.dumps(res), file=f, flush=attempt==ns.classification_attempts-1)
            print_progress(i*ns.classification_attempts + attempt, runs, start_time)

    if ns.output != '-':
        f.close()
