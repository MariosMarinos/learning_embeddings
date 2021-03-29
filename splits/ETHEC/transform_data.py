import json
import sys
import numpy as np

def load_tester(path):
    with open(path) as f:
        data = json.load(f)
    return np.asarray(data)

if __name__ == "__main__" :
    arr = load_tester(sys.argv[1])
    with open(sys.argv[2], 'wb') as f:
        np.save(f, arr)

