"""Sample file intentionally containing issues for the analyzer to catch."""

import os           # used
import sys          # unused
import json         # unused
from pathlib import Path  # used
from collections import OrderedDict  # unused


def short_func(x):
    return x * 2


def long_function(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item)
        elif item == 0:
            result.append(0)
        else:
            result.append(-item)

    total = sum(result)
    average = total / len(result) if result else 0
    minimum = min(result) if result else None
    maximum = max(result) if result else None

    summary = {
        "total": total,
        "average": average,
        "min": minimum,
        "max": maximum,
        "count": len(result),
    }
    return summary


def greet(name):
    path = Path("/tmp") / name
    base = os.path.basename(str(path))
    return f"Hello, {base}"
