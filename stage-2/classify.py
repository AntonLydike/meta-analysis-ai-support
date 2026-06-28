import argparse
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Generator, Literal

from openai import OpenAI
import openai
from pydantic import BaseModel, Field

from tools import Document, load_rdf

# =====================================================================
# 1. Structure Definitions (Config & Document)
# =====================================================================


@dataclass(frozen=True)
class Model:
    name: str
    input_price: float
    cached_price: float
    out_price: float

    def __str__(self) -> str:
        return self.name


models = {
    m.name: m
    for m in sorted(
        [
            Model("gpt-5.4-mini", 0.75, 0.075, 4.5),
            Model("gpt-5.4", 2.5, 0.25, 15.0),
            Model("gpt-5.5", 5.0, 0.50, 30.0),
            Model("gpt-5.4-nano", 0.20, 0.02, 1.25),
        ],
        key=lambda m: m.name,
        reverse=True,
    )
}


@dataclass
class Config:
    prompt: str
    model: Model = models["gpt-5.4-mini"]
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    max_tokens: int = 1000
    poll_interval_seconds: int = 10


# =====================================================================
# 2. Main Processing Function
# =====================================================================


def score_documents(
    config: Config, docs: list[Document], schema: type[BaseModel]
) -> Generator[dict[int, dict | None], None, None]:
    """
    Fires off batched document scoring requests to OpenAI using their official Batch API.
    Embeds the text directly into the text conversational payload.
    """
    client = OpenAI(api_key=config.api_key)

    # Official OpenAI Batch Limits
    MAX_REQUESTS_PER_BATCH = 50_000
    MAX_FILE_SIZE_BYTES = (
        190 * 1024 * 1024
    )  # 190 MB safety margin (API absolute ceiling is 100MB)

    current_batch_lines: list[bytes] = []
    current_batch_doc_ids: list[int] = []
    current_batch_size = 0
    all_submitted_batches: list[dict[str, Any]] = []
    schema_json = {
        "name": "document_scoring",
        "strict": True,
        "schema": schema.model_json_schema(),  # assuming 'schema' is your Pydantic model class
    }
    schema_json["schema"]["additionalProperties"] = False

    print(f"📦 Compiling {len(docs)} text documents into batch payloads...")

    # Step A: Sequentially build and group payloads to respect limits
    for doc in docs:
        try:
            # Construct standard endpoint parameters matching OpenAI JSONL schema targets
            line_dict = {
                "custom_id": f"doc_{doc.id}",  # Prefixing with a string prevents loose data type validation errors
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": config.model.name,
                    "max_completion_tokens": config.max_tokens,
                    "reasoning_effort": "low",  # Enforces low reasoning paths for o-series endpoints
                    "response_format": {
                        "type": "json_schema",  # REQUIRED for structured JSON mapping
                        "json_schema": schema_json,
                    },
                    "messages": [
                        {"role": "system", "content": config.prompt},
                        {
                            "role": "user",
                            "content": f"title: {doc.title}, authors: {doc.authors}\ncontent:\n\n{doc.get_text()}",
                        },
                    ],
                },
            }
            # Encode line to compute real-time physical bytes consumption
            encoded_line = (json.dumps(line_dict) + "\n").encode("utf-8")
            line_size = len(encoded_line)

            # Boundary Check: If adding this document breaks batch constraints, dispatch the current batch
            if (
                len(current_batch_lines) + 1 > MAX_REQUESTS_PER_BATCH
                or current_batch_size + line_size > MAX_FILE_SIZE_BYTES
            ):

                # Dispatch batch (In Series)
                batch_info = _submit_openai_batch(
                    client, current_batch_lines, current_batch_doc_ids
                )
                all_submitted_batches.append(batch_info)

                # Reset tracking variables for next block cluster
                current_batch_lines = [encoded_line]
                current_batch_doc_ids = [doc.id]
                current_batch_size = line_size
            else:
                current_batch_lines.append(encoded_line)
                current_batch_doc_ids.append(doc.id)
                current_batch_size += line_size

        except Exception as e:
            print(f"❌ Failed processing document ID {doc.id} ('{doc.title}'): {e}")
            import traceback

            traceback.print_exc()

    # Dispatch any remaining documents sitting in the buffer
    if current_batch_lines:
        batch_info = _submit_openai_batch(
            client, current_batch_lines, current_batch_doc_ids
        )
        all_submitted_batches.append(batch_info)

    # Step B: Parallel Active Monitoring Loop
    print("\n🚀 All text batches submitted. Monitoring jobs concurrently...")
    yield from _poll_and_retrieve_batches_parallel(
        client, all_submitted_batches, config
    )


# =====================================================================
# 3. Pipeline Orchestration Helpers
# =====================================================================


def _submit_openai_batch(
    client: OpenAI, lines: list[bytes], doc_ids: list[int]
) -> dict[str, Any]:
    """Uploads the file and submits the batch to OpenAI."""
    # Build in-memory bytes layout buffer
    io_buffer = io.BytesIO(b"".join(lines))
    io_buffer.name = "batch_input.jsonl"

    print(f"📤 Uploading batch manifest containing {len(doc_ids)} documents...")
    uploaded_file = client.files.create(file=io_buffer, purpose="batch")

    batch_job = client.batches.create(
        input_file_id=uploaded_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    print(f"✅ Batch successfully launched! ID: {batch_job.id}")
    return {"batch_id": batch_job.id, "tracked_doc_ids": doc_ids}


def _poll_and_retrieve_batches_parallel(
    client: OpenAI,
    batches: list[dict[str, Any]],
    config: Config,
) -> Generator[dict[int, dict | None], None, None]:
    """Monitors running jobs in parallel using thread pools, yielding parsed JSON blocks."""
    pending_batches = {b["batch_id"]: b["tracked_doc_ids"] for b in batches}
    completed_batches = []

    while pending_batches:
        time.sleep(config.poll_interval_seconds)
        statuses = {}
        completed_this_round = []

        # Poll all batch statuses concurrently
        with ThreadPoolExecutor(max_workers=min(len(pending_batches), 16)) as executor:
            future_to_id = {
                executor.submit(client.batches.retrieve, b_id): b_id
                for b_id in pending_batches.keys()
            }
            for future in as_completed(future_to_id):
                b_id = future_to_id[future]
                try:
                    statuses[b_id] = future.result()
                except Exception as ex:
                    print(f"⚠️ Status check communication lag on batch {b_id}: {ex}")

        # Summary Log Screen UI
        print(
            f"\n--- ⏳ Cluster Execution Progress Summary ({time.strftime('%X')}) ---"
        )
        for b_id, b_obj in statuses.items():
            print(
                f"Batch {b_id} [{b_obj.request_counts.completed} / {b_obj.request_counts.failed} / {b_obj.request_counts.total}]: Status is '{b_obj.status.upper()}'"
            )
            if b_obj.status in ["completed", "failed", "expired", "cancelled"]:
                completed_this_round.append((b_id, b_obj))

        # Unload finished jobs and stream yields immediately
        for b_id, b_obj in completed_this_round:
            original_doc_ids = pending_batches.pop(b_id)
            completed_batches.append(b_obj)
            yield _download_and_collate_results(client, b_obj, original_doc_ids)

    print_total_batch_costs(completed_batches, config.model)


def _download_and_collate_results(
    client: OpenAI, batch_obj: Any, original_ids: list[int]
) -> dict[int, dict | None]:
    """Downloads individual finished payloads and extracts JSON matching structural schemas."""
    # Initialize dictionary mapping tracking positions to None as an default fallback
    results_map: dict[int, dict | None] = {i: None for i in original_ids}

    if batch_obj.status != "completed" or not batch_obj.output_file_id:
        print(
            f"🛑 Batch job {batch_obj.id} finished with an invalid status: {batch_obj.status}"
        )
        return results_map

    try:
        file_response = client.files.content(batch_obj.output_file_id)

        for line in file_response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            doc_id = int(data.get("custom_id", "").removeprefix("doc_"))
            try:
                message_content = data["response"]["body"]["choices"][0]["message"][
                    "content"
                ]
                if message_content:
                    results_map[doc_id] = json.loads(message_content)
            except (KeyError, TypeError, json.JSONDecodeError) as e:
                results_map[doc_id] = None
                print(f"Error getting result for doc: {doc_id}: ", e)
                import traceback

                traceback.print_exception(e)

    except Exception as e:
        print(
            f"💥 Critical error extracting result content from file {batch_obj.output_file_id}: {e}"
        )

    return results_map


# cost tracking:
def print_total_batch_costs(completed_batch_objects: list[Any], model: Model):
    """
    Calculates detailed metrics and total financial costs from b.usage objects.

    Rates (gpt-5.4-mini baseline):
      - Standard Input:     $0.75 / 1M tokens
      - Cached Input:       $0.075 / 1M tokens (90% off standard)
      - Output/Reasoning:   $4.50 / 1M tokens

    * OpenAI natively applies a flat 50% discount on all Batch API usage.
    """
    total_input_tokens = 0
    total_cached_tokens = 0
    total_output_tokens = 0
    total_reasoning_tokens = 0

    for batch in completed_batch_objects:
        usage = getattr(batch, "usage", None)
        if not usage:
            continue

        # 1. Gather all Input Metrics
        # Note: input_tokens represents the absolute total. Uncached = Total - Cached
        current_total_in = getattr(usage, "input_tokens", 0)

        in_details = getattr(usage, "input_tokens_details", None)
        current_cached = getattr(in_details, "cached_tokens", 0) if in_details else 0

        total_cached_tokens += current_cached
        total_input_tokens += (
            current_total_in - current_cached
        )  # Store pure uncached input

        # 2. Gather all Output Metrics
        total_output_tokens += getattr(usage, "output_tokens", 0)

        out_details = getattr(usage, "output_tokens_details", None)
        if out_details:
            total_reasoning_tokens += getattr(out_details, "reasoning_tokens", 0)

    # Calculate standard costs at base tier rates
    gross_uncached_in_cost = (total_input_tokens / 1_000_000) * model.input_price
    gross_cached_in_cost = (total_cached_tokens / 1_000_000) * model.cached_price
    gross_output_cost = (total_output_tokens / 1_000_000) * model.out_price

    gross_total = gross_uncached_in_cost + gross_cached_in_cost + gross_output_cost

    # Apply the Batch API 50% discount multiplier
    actual_billable_cost = gross_total * 0.5

    # Print out summary report matrix
    print("\n" + "=" * 55)
    print("💵 FINANCIAL API PIPELINE RUN METRICS SUMMARY")
    print("=" * 55)
    print(f" Uncached Input Tokens:       {total_input_tokens:,}")
    print(f" Cached Input Tokens (Hit):   {total_cached_tokens:,}")
    print(f" Total Output Tokens:         {total_output_tokens:,}")
    print(f"   └─ Includes Reasoning:     {total_reasoning_tokens:,}")
    print("-" * 55)
    print(f" Gross Standard Cost:         ${gross_total:.4f}")
    print(
        f" Actual Billable Batch Cost:  ${actual_billable_cost:.4f} (50% Off Applied)"
    )
    print("=" * 55)


class DocumentScoringSchema(BaseModel):
    document_type: Literal[
        "empirical study", "abstract only", "dissertation", "letter", "missing", "other"
    ] = Field(..., description="How complete the document text is.")

    source_language: str = Field(
        ...,
        description="The ISO language code of the primary text (e.g., 'en', 'fr', 'de').",
    )

    reasoning: str = Field(
        ...,
        description="Text explaining the reasoning behind the chosen classification result.",
    )

    classification_result: Literal[
        "Exclude: Wrong Format",
        "Exclude: Wrong Language",
        "Exclude: Sample Mismatch",
        "Exclude: Lacking SWB",
        "Exclude: Lacking RRS",
        "Exclude: Lacking Effect Size",
        "Include",
    ] = Field(
        ...,
        description="The final screening classification for this document based on the study criteria.",
    )


PROMPT = """
You are conducting a meta-analysis on the relationship between romantic relationship status and subjective well-being. You are performing full-text screening to decide whether to INCLUDE or EXCLUDE a given paper. Consider the following criteria carefully, you must be able to explain and justify each decision made.

### **Inclusion Criteria**
- Participants: Human adults (age ≥ 16).
- Relationship Status: Must include a measure of romantic relationship status (e.g., single, partnered, dating, divorced, married, cohabiting, living alone), EVEN IF it is only used as a covariate/control variable.
- Subjective Well-Being : Must include a measure of subjective well-being (e.g., life satisfaction, positive affect, negative affect, happiness, or a validated subjective well-being scale), EVEN IF it is only used as a covariate/control variable.
- Variable Variance: The romantic relationship status variable CANNOT be invariant (i.e., studies where 100% of the sample shares the same status, such as all-single or all-married samples, must be excluded).
- Language: Must be peer-reviewed journal articles published in English.

### Exclusion Criteria
- Study Type: Non-empirical or purely qualitative studies (including systematic reviews, scoping reviews, meta-analyses, commentaries, editorials, errata, and bibliometric analyses).
- Grey Literature: Dissertations, theses, conference abstracts, and unpublished reports.
- Sample Type: Studies based entirely on clinical samples (e.g., studies where ALL participants are cancer patients, individuals with diabetes, or clinical psychiatric patients).
- Language: Articles that are not in English
- Wrong Measures: Studies that measure only health-related or general quality of life (e.g., EQ-5D, EQ-VAS, SF-12, SF-36, WHOQOL, WHOQOL-BREF, SEIQoL) and not subjective well-being should be excluded unless the instrument explicitly measures life satisfaction, positive affect, negative affect, happiness, or subjective well-being.

---

### Possible Calssifacation Results:
1. Wrong Format: The work is not a peer-reviewed journal article of an empirical study (e.g. conference abstract only, dissertation, thesis, book chapter, grey literature, editorial letter, commentary, or purely qualitative research).
2. Wrong Language: The full text or core study is not in English.
3. Sample Mismatch:
  - The participants are entirely from a clinical population (e.g., cancer patients, diabetes patients, psychiatric patients);
  - OR participants' age is below 16.
4. Lacking SWB: The study lacks a measure of subjective well-being (SWB) or measures unrelated quality of life measure.
5. Lacking RRS: The study does not include any measure of romantic relationship status (RRS), OR the relationship status variable is invariant (e.g., all participants are married, widowed, or single).
6. Lacking Effect Size: No effect size is reported or can reasonably be derived from the reported statistics (e.g., no means/SDs, correlations, regression coefficients, contingency tables, or other convertible statistics).

---

### Your Task & Output Format
Please read the provided full text documents, paying attention to all criteria stated above. Make sure to check all possible reasons for exclusion first before considering an article for inclusion. Once a conclusion has been reached, you must respond in structured JSON respecting the provided schema.
"""


def run(args: argparse.Namespace):
    docs: list[Document] = load_rdf(args.rdffile)

    if args.trial_limit:
        docs = docs[: args.trial_limit]
        print(f"🧪 limiting to {len(docs)} docs")

    if not args.from_checkpoint:
        conf = Config(
            prompt=PROMPT,
            model=args.model,
        )

        batches = []
        for res in score_documents(conf, docs, DocumentScoringSchema):
            batches.append(res)

        print(f"checkpointing at {args.checkpoint}")
        with open(args.checkpoint, "w") as f:
            json.dump(batches, f)
    else:
        with open(args.checkpoint, "r") as f:
            batches = json.load(f)

    if args.html:
        print("creating html summary")
        with open(args.html, "w") as f:
            f.write(generate_html_result(docs, batches))


def costs(args: argparse.Namespace):
    """
    Takes a list of raw Batch IDs, retrieves their live objects from OpenAI,
    polls until they reach a final state, and returns the full object list
    for immediate cost analysis or collation testing.
    """
    client = OpenAI()
    completed_batch_objects = []

    # Track which batch IDs we are still waiting on
    batch_ids = args.batch_ids
    active_batch_ids = list(batch_ids)

    print(f"🔄 Attaching to {len(batch_ids)} historical batch runs...")

    while active_batch_ids:
        still_running = []

        for b_id in active_batch_ids:
            try:
                # Pull the raw object state directly from OpenAI
                batch_obj = client.batches.retrieve(b_id)
                status = batch_obj.status.upper()

                print(f"  • Batch {b_id} current status: [{status}]")

                # Check if it has reached a terminal state
                if status in ["COMPLETED", "FAILED", "EXPIRED", "CANCELLED"]:
                    completed_batch_objects.append(batch_obj)
                else:
                    # Keep it in our loop queue if it's still running
                    still_running.append(b_id)

            except Exception as e:
                print(f"❌ Error retrieving batch state for {b_id}: {e}")

        active_batch_ids = still_running

        # If we are still waiting on some batches, pause before polling again
        if active_batch_ids:
            print(
                "⏳ Some batches are still processing. Checking status again in 20 seconds..."
            )
            time.sleep(5)
            print("\n--- 🔄 Live Polling Refresh ---")

    print("\n🏁 All specified batches have reached a final state.")

    # 💥 Call your updated cost function directly using the pulled live states
    print_total_batch_costs(completed_batch_objects, args.model)


def errors(args: argparse.Namespace):
    c = openai.Client()
    for id in args.batch_ids:
        batch = c.batches.retrieve(id)
        if batch.error_file_id is None:
            continue
        print(f"---{id}---")
        print(c.files.content(batch.error_file_id).text)


if __name__ == "__main__":
    from to_html import generate_html_result

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    runparser = subparsers.add_parser("run", help="run classification on rdf dump")
    runparser.set_defaults(fn=run)
    runparser.add_argument("rdffile", help="rds zotero export")
    runparser.add_argument("--html", default=None, help="generate HTML report")
    runparser.add_argument(
        "--model",
        choices=models.values(),
        help="Select a model",
        default=Config.model,
        type=lambda name: models.get(name),
    )
    runparser.add_argument(
        "--trial-limit",
        type=int,
        help="limit number of docs to this number for a test run",
        default=None,
        nargs="?",
    )
    runparser.add_argument(
        "--checkpoint", default="checkpoint.json", help="batch checkpointing file"
    )
    runparser.add_argument(
        "--from-checkpoint",
        default=False,
        action="store_true",
        help="continue from prior checkpoint",
    )

    costparser = subparsers.add_parser("cost")
    costparser.set_defaults(fn=costs)
    costparser.add_argument(
        "batch_ids", nargs="+", help="batch ids to print cost summaries for"
    )
    costparser.add_argument(
        "--model",
        choices=models.values(),
        help="Select a model",
        default=Config.model,
        type=lambda name: models.get(name),
    )

    errparser = subparsers.add_parser("errors")
    errparser.set_defaults(fn=errors)
    errparser.add_argument("batch_ids", nargs="+", help="batch ids to print errors for")

    args = parser.parse_args()
    args.fn(args)
