from dataclasses import dataclass
import tempfile, os, json
import time
from typing import Generator
from aalib.progress import progress


from webapp.db import get_connection, items_left_in_job
from pydantic import BaseModel
from openai import OpenAI

OPENAI_MODELS = (
    'gpt-5',
    'gpt-5-mini',
    'gpt-5-nano',
)

# structure for output
class ScoringResult(BaseModel):
    reason: str
    """
    Reasoning behind given score.
    """
    score: int
    """
    Output score between 0 and 100.
    """


def build_jsonl_doc(job_id: str, i: int, prompt: str, model: str, elm) -> str:
    """
    Build the document for the 
    """
    return json.dumps(
        {
            "custom_id": f"batch:{job_id}:{elm["id"]}:{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": f"title: '{elm["title"]}'\nabstract:\n{elm["abstract"]}"
                    }
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ScoringResult",
                        "schema": ScoringResult.model_json_schema(),
                    },
                },
                "reasoning_effort": "minimal",
                "max_completion_tokens": 2000,
            },
        }
    )


CHUNK_LIMIT = 2e8
CHUNK_ELM_LIMIT = 50000


def process_batch(
    job_id: str,
    name: str,
    model: str,
    prompt: str,
    repeats: int,
    update_job_progress,
):
    with tempfile.TemporaryDirectory(prefix="oai-batch-") as dir:
        # state vars
        chunk_num = 0
        chunk_size = 0
        chunk_elems = 0
        # chunk file vars
        chunk_name = f"batch-{job_id}-{chunk_num}.jsonl"
        chunk_files = [chunk_name]
        chunk_file = open(os.path.join(dir, chunk_name), "w")
        # write chunks to disk:
        for i, elm in enumerate(items_left_in_job(job_id, repeats)):
            doc = build_jsonl_doc(job_id, i, prompt, model, elm)

            # make new chunk if chunk is full
            if (
                len(doc.encode()) + chunk_size > CHUNK_LIMIT
                or chunk_elems >= CHUNK_ELM_LIMIT
            ):
                chunk_file.close()
                chunk_num += 1
                chunk_name = f"batch-{job_id}-{chunk_num}.jsonl"
                chunk_files.append(chunk_name)
                chunk_file = open(os.path.join(dir, chunk_name), "w")
                chunk_size = 0
                chunk_elems = 0
            # use print to add newlines
            print(doc, file=chunk_file)
            chunk_size += len(doc.encode())
            chunk_elems += 1
        # close last file
        chunk_file.close()

        print(f"created batch files: {chunk_files}")

        # create openai client
        client = OpenAI()

        t0 = time.time()
        # launch and monitor batches now:
        batch_ids = [launch_batch(client, dir, chunk) for chunk in chunk_files]

        print(f"launched batches: {batch_ids}")
        print("=" * 60)

        # check progress:
        while True:
            time.sleep(5)

            status = print_batch_status(client, batch_ids, update_job_progress, job_id, t0)

            # Exit loop if all batches are done
            if all(s.is_done for s in status):
                print("All batches have reached a terminal state.")
                break

        # write results to database:
        import_batch_results(client, batch_ids)


def launch_batch(client: OpenAI, base_dir: str, batch_file: str) -> str:
    """
    Uploads the batch file to OpenAI and creates a batch job.
    Returns the batch id.
    """
    # Upload the JSONL file first
    file_path = os.path.join(base_dir, batch_file)
    with open(file_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")

    # Create the batch job pointing at chat/completions
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",  # batches must have a window (1h, 24h)
    )

    return batch.id


@dataclass
class BatchStatus:
    id: str
    total: int
    completed: int
    failed: int
    is_done: bool
    completion_state: str


def get_batch_status(client: OpenAI, batches: list[str]) -> list[BatchStatus]:
    """
    Get the status from OpenAI for a list of batch IDs.
    Returns a list of BatchStatus objects with counts and completion flag.
    """
    results: list[BatchStatus] = []

    for batch_id in batches:
        batch = client.batches.retrieve(batch_id)

        total = batch.request_counts.total or 0
        completed = batch.request_counts.completed or 0
        failed = batch.request_counts.failed or 0

        # Track the raw completion state
        state = batch.status
        is_done = state in ("completed", "failed", "expired", "cancelled")

        results.append(
            BatchStatus(
                id=batch.id,
                total=total,
                completed=completed,
                failed=failed,
                is_done=is_done,
                completion_state=state,
            )
        )

    return results

@dataclass
class ClassificationResult:
    job_id: str
    elm_id: str
    completion_time: float
    score: int
    reason: str
    token_usage: dict


def print_batch_status(client: OpenAI, batch_ids: list[str], update_job_progress = None, job_id = None, t0 = None):
    status = get_batch_status(client, batch_ids)

    total = sum(s.total for s in status)
    completed = sum(s.completed for s in status)
    failed = sum(s.failed for s in status)

    # Build a per-batch breakdown
    batch_lines = []
    for s in status:
        batch_lines.append(
            f"[{s.id}] {s.completed}/{s.total} completed, "
            f"{s.failed} failed, state={s.completion_state}"
        )

    # Overall summary
    print(f"Overall progress: {completed}/{total} completed, {failed} failed")
    print("Per-batch details:")
    print("\n".join(batch_lines))
    print("=" * 60)

    if update_job_progress:
        update_job_progress(job_id, completed + failed, time.time() - t0)

    return status

def parse_batch_results(client: OpenAI, batch_ids: list[str]) -> Generator[ClassificationResult, None, None]:
    """
    Download completed batch results and return a list of ClassificationResult objects.
    Uses the 'created' field as completion_time and 'usage.total_tokens' for tokens_used.
    Prints errors for malformed lines or missing fields.
    """
    for batch_id in batch_ids:
        batch = client.batches.retrieve(batch_id)

        if batch.status != "completed":
            print(f"Skipping batch {batch_id}: not completed (status={batch.status})")
            continue

        file_id = batch.output_file_id

        if file_id is None:
            print(f"Batch {batch_id} has no output file, skipped")
            continue 

        for idx, line in enumerate(client.files.content(file_id).iter_lines(), 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"JSON decode error in batch {batch_id}, line {idx}: {e}")
                continue

            custom_id = data.get("custom_id")
            if not custom_id:
                print(f"Missing custom_id in batch {batch_id}, line {idx}")
                continue

            try:
                _, job_id, elm_id, _ = custom_id.split(":")
            except ValueError:
                print(f"Malformed custom_id '{custom_id}' in batch {batch_id}, line {idx}")
                continue

            response_body = None
            try:
                response_body = data["response"]["body"]
            except KeyError:
                print(f"Missing response body in batch {batch_id}, line {idx}")
                continue

            # Extract completion timestamp
            completion_time = response_body.get("created")
            if completion_time is None:
                print(f"Missing 'created' timestamp in batch {batch_id}, line {idx}")
                completion_time = 0

            # Extract usage tokens
            usage = response_body.get("usage", {})

            # Extract structured output
            output = response_body.get("choices", [{}])[0].get('message', {}).get('content')
            if not output:
                print(f"Missing output in batch {batch_id}, line {idx}")
                continue

            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                print(f"Malformed json: {output} on request {line} (line {idx})")
                continue

            score = output.get("score", None)
            reason = output.get("reason", None)
            if score is None or reason is None:
                print(f"Incomplete output in batch {batch_id}, line {idx}: {output}")
                continue

            yield ClassificationResult(
                job_id=job_id,
                elm_id=elm_id,
                completion_time=completion_time,
                score=score,
                reason=reason,
                token_usage=usage,
            )


def import_batch_results(client: OpenAI, batch_ids: list[str]):
    count = 0
    ttl = sum(b.completed for b in get_batch_status(client, batch_ids))
    print("starting import")
    conn = get_connection()
    for res in progress(parse_batch_results(client, batch_ids), count=ttl):
        conn.execute('INSERT INTO reviews (publication_id, job_id, created, rating, reason, raw_data) VALUES (?,?,?,?,?,?)', (
            res.elm_id,
            res.job_id,
            res.completion_time,
            res.score,
            res.reason,
            json.dumps(res.token_usage)
        ))
        count += 1
        if count >= 1000:
            count = 0
            conn.commit()
    conn.commit()
    print("Completed!")

# prices per 1m tokens
PRICES = {
    'gpt-5-nano': {
        'input': 0.05,
        'output': 0.4,
        'input_cached': 0.005,
    },
    'gpt-5-mini': {
        'input': 0.25,
        'output': 2.0,
        'input_cached': 0.025,
    },
    'gpt-5': {
        'input': 1.25,
        'output': 10.0,
        'input_cached': 0.125,
    }
}

def calculate_price(model: str, usage: dict, batch: bool = True):
    price = PRICES.get(model)

    cached = usage.get('input_tokens_details', {}).get('cached_tokens', 0)
    input = usage.get('input_tokens', 0) - cached
    output = usage.get('output_tokens')

    return sum((
        (input / 1e6) * price.get('input'),
        (output / 1e6) * price.get('input'),
        (cached / 1e6) * price.get('input_cached'),
    )) + 0.5 if batch else 1


def total_batch_price(client: OpenAI, model: str, batch_ids: list[str]):
    ttl = 0
    for id in batch_ids:
        batch = client.batches.retrieve(id)
        ttl += calculate_price(model, batch.usage, batch=True)
    return ttl


if __name__ == '__main__':
    import sys
    client = OpenAI()
    match sys.argv[1:]:
        case ["status", *batch_ids]:
            print("=" * 60)
            print_batch_status(client, batch_ids)
        case ["import", *batch_ids]:
            import_batch_results(client, batch_ids)
        case ["pricing", model, *batch_ids]:
            print(f"Total cost: ${total_batch_price(client, model, batch_ids)}")
        case default:
            print("unknown command")
