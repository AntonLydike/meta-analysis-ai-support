# Classify Bibliography based on Study Relevance

This is a thin script around ollama to try and classify a bibliography file into relevant and not-so-relevant parts.

## Usage:

If you bring your own models, you need to modify the `MODELS` variable in `classify.py`. You probably also want to change the default ollama url configured.

Then, you get your bibliography file ready (make sure it is the same file used across all attempts so that results can be combined later on). Our bibliography file's sha1 is `a1a1a6d8d1f46cf1b6a9f82f30e5c0e74d81d87d`.

Then you can run the file using `python classify.py -i bibliography.txt -o llama3.jsonl -m llama3.1:8b`.

More options are:
- `-k` classify every document `k` times
- `-c` classify `c` number of documents (e.g. for a test run, only run on 10 documents by using `-c 10`)
- `--stream` output the model content as well to double check
- `--ollama-host` configure the ollama endpoint

You can resume a partial run by providing the same output file. The script will scan for the last document id processed and continue from there. This is useful for when a run got interrupted, or a computer crashed for example.
