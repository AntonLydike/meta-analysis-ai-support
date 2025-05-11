import sys
import json
import rispy
import random
import argparse


def reservoir_sample(data: list, k: int, seed: int):
    rng = random.Random(seed)

    output = []
    for i in range(k):
       output.append(data[i])
    
    for i in range(k, len(data)):
       index = rng.randint(0, i)
       if index < k:
          output[index] = data[i]

    return output

if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('-i', '--input', help="input file to read")
    args.add_argument('-k', '--sample-size', help="Size of the sample to take. Fractions will be interpreted as percentages.", type=str)
    args.add_argument('-s', '--seed', help="Seed for the RNG (default = 0)", default=0)
    args.add_argument('-f', '--format', choices=('jsonl', 'json', 'ris'), default=None, help="output format")
    args.add_argument('-o', '--output', help="output file")

    ns = args.parse_args()

    print("Loading bibliography...", file=sys.stderr)
    filepath = ns.input
    with open(filepath, 'r') as bibliography_file:
        entries = rispy.load(bibliography_file)

    if '.' in ns.sample_size or 'e' in ns.sample_size:
        samples = int(len(entries) * float(ns.sample_size))
    else:
        samples = int(ns.sample_size)
    
    print('Sampling....', file=sys.stderr)
    sample = reservoir_sample(entries, samples, ns.seed)

    # grab the format specifier
    f = ns.format
    # if it's not set, but we have an output file, infer from file ending
    if f is None and ns.output is not None:
        if ns.output.endswith('json'):
            f = 'json'
        elif ns.output.endswith('jsonl'):
            f = 'jsonl'
    # if nothing is given, and nothing can be inferred, use ris
    if f is None:
        f = 'ris'
    
    out = sys.stdout
    if ns.output is not None:
        out = open(ns.output, 'w')

    print('Writing....', file=sys.stderr)

    if f == 'ris':
        rispy.dump(sample, out)
    elif f == 'json':
        json.dump(sample, out)
    elif f == 'jsonl':
        for l in sample:
            print(json.dumps(l), file=out)
