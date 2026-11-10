"""Small-sample statistics for the comparison tables (standard library only).

Each system is run once on 40 core and 12 challenge cases, so raw accuracy
differences of one or two cases are easy to over-read. The report therefore adds
  * a 95% Wilson score interval for every accuracy (stable for n < 50 and p near 0/1), and
  * an exact two-sided McNemar test on the paired per-case outcomes of our agent vs
    each baseline (same cases, so only the discordant cases carry information).
"""
from math import comb, sqrt

Z_95 = 1.959964


def wilson_ci(successes, n, z=Z_95):
    """95% Wilson score interval for a binomial proportion; (0, 0) when n == 0."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(only_a, only_b):
    """Exact two-sided McNemar p-value.

    only_a: cases system A got right and B got wrong; only_b: the reverse.
    Under H0 the discordant cases split 50/50, so p = two-sided binomial tail.
    """
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_outcomes(rows_a, rows_b, key):
    """Discordant counts (A right & B wrong, B right & A wrong) over the cases both systems ran."""
    b_by_case = {r["case_id"]: r for r in rows_b}
    only_a = only_b = 0
    for ra in rows_a:
        rb = b_by_case.get(ra["case_id"])
        if rb is None:
            continue
        a_ok, b_ok = key(ra), key(rb)
        only_a += a_ok and not b_ok
        only_b += b_ok and not a_ok
    return only_a, only_b
