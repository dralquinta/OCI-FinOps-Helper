"""Bounded scheduling for expensive OCI collection scopes."""

from collections import deque
from itertools import islice


def bounded_map(executor, function, iterable, max_pending):
    """Yield results in input order while keeping at most max_pending futures.

    Unlike Executor.map on supported Python versions, this consumes scopes
    incrementally so a slow first scope cannot retain the entire run backlog.
    """
    if max_pending < 1:
        raise ValueError('max_pending must be positive')
    remaining = iter(iterable)
    pending = deque(executor.submit(function, item)
                    for item in islice(remaining, max_pending))
    while pending:
        future = pending.popleft()
        yield future.result()
        for item in islice(remaining, 1):
            pending.append(executor.submit(function, item))
