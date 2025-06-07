import sys
import time
from aalib.progress import progress
import ollama




if __name__ == '__main__':
    c = ollama.Client()
    avg = []
    for _ in range(int(sys.argv[-1])):
        t = time.time()
        r = c.generate('llama3.2:3b', prompt="Generate 100 random numbers between 0 and 1, no text, as a JSON array.")['response']
        speed = len(r) / (time.time() - t)
        print(f"speed: {speed}")
        print(r)
        avg.append(speed)
        avg = avg[:10]
        print(f"average: {sum(avg)/len(avg)}")

