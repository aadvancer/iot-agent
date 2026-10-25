"""Retrieval sanity check for the knowledge base (top-1 / top-3 hit rate).
Each probe lists the chunk titles (substrings) that count as relevant.
Run after editing the KB: python -m eval.retrieval_check"""
from env.knowledge_base import get_kb

PROBES = {
    "camera intermittently offline weak signal": ["Wireless range", "H-01"],
    "cannot add new sensor pairing fails error E-201": ["E-201", "Device capacity", "H-02"],
    "sensor stopped sending alerts after base station update E-305": ["E-305", "H-07", "Peripheral firmware"],
    "old indoor camera offline after firmware update no OTA": ["Peripheral firmware", "H-03", "E-305", "Firmware update"],
    "three sensors offline at the same time": ["E-610", "H-05"],
    "events not uploaded to cloud": ["E-503", "H-06"],
    "battery camera misses events": ["Battery cameras"],
    "all devices offline red light": ["Network uplink", "LED status", "H-04"],
    "when should I escalate to FAE": ["Escalate to FAE", "Purpose"],
    "recordings stopped storage": ["Local storage", "E-402"],
    "device shown in app but missing from base station": ["E-207", "Factory reset of a peripheral"],
    "camera fails even next to base after reset": ["Escalate to FAE", "Factory reset of a peripheral"],
}


def main():
    kb = get_kb()
    top1 = top3 = 0
    for query, gold in PROBES.items():
        titles = [h["title"] for h in kb.search(query, k=3)]
        rel = [any(g in t for g in gold) for t in titles]
        top1 += bool(rel) and rel[0]
        top3 += any(rel)
        if not any(rel):
            print(f"  miss: {query!r} -> {titles}")
    n = len(PROBES)
    print(f"[retrieval] {len(kb.chunks)} chunks | top-1 {top1}/{n} | top-3 {top3}/{n}")


if __name__ == "__main__":
    main()
