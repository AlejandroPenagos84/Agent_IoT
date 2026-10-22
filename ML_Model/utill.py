import pandas as pd
from collections import Counter
import math

# Get Entropy of a text
def entropy(texto):
    if pd.isna(texto) or not str(texto):
        return 0.0
    text = str(texto)
    probs = [count / len(text) for count in Counter(text).values()]
    return -sum(p * math.log2(p) for p in probs)