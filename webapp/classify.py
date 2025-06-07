from dataclasses import dataclass
import os
import asyncio
import re
import json
import sqlite3
import time
import ollama

from webapp.db import get_connection

JSON_REGEX = re.compile(r'```(json)?\n(\{.*\})\n```', flags=re.DOTALL)


def classify_work(chat: ollama.Client, prompt: str, model: str, work: dict) -> dict | None:
    res = chat.generate(
        model=model, 
        prompt=prompt.format(title=work['title'], abstract=work['abstract']),
        stream=False
    )
    text = res['response']
    
    # read JSON from response
    data = extract_json(text)
    if data is None:
        # try to rescure the JSON from the response body
        new_text = chat.generate(
            model=model,
            prompt=f'Please extract the JSON from the following response body, make sure it\'s properly enclosed in three backticks and a json tag, following the schema `{{"score": Number, "reason": String}}`. Leave an empty response if no JSON can be found or fields are missing.\n\n---\n{text}'
        )['response']
        data = extract_json(new_text)
        # fail if second extraction did not work
        if data is None:
            return None
        data['re_extract'] = True
    
    if 'score' not in data or 'reason' not in data:
        return None

    data['re_extract'] = data.get('re_extract', False )
    
    data['full_text'] = text
    return data



def extract_json(text: str) -> dict | None:
    if (match := JSON_REGEX.search(text)) is None:
        return None
    try:
        res = json.loads(match.group(2))
        if not isinstance(res, dict):
            return None
        if 'score' not in res or 'reason' not in res:
            return None
        if not isinstance(res['score'], int):
            return None
        return res
    except json.JSONDecodeError:
        return None


def process_item(client: ollama.Client, job_id: str, name: str, model: str, prompt: str, pub: sqlite3.Row):
    res = classify_work(client, prompt, model, pub)

    # skip broken model output
    if res is None:
        return False

    res['id'] = pub['id']
    res['model'] = model

    conn = get_connection()
    conn.execute('INSERT INTO reviews (publication_id, job_id, created, rating, reason, raw_data) VALUES (?,?,?,?,?,?)', (
        pub['id'],
        job_id,
        time.time(),
        res['score'],
        res['reason'],
        json.dumps(res),
    ))
    conn.commit()
    return True


def get_ollama() -> ollama.Client:
    return ollama.Client(host=os.environ['OLLAMA_HOST'])
