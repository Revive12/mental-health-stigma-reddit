"""Generate fictional labeled comments for offline smoke tests; no real users or quotations."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="outputs/synthetic_labeled.jsonl")
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as stream:
        for p in range(48):
            post = f"t3_synthetic{p:03d}"
            sub = "depression" if p < 24 else "AskReddit"
            rows = []
            for a, label in enumerate("ABCDEFGH"):
                parent = f"t1_synthetic{p:03d}p{a}"
                author = f"t2_synthetic_author_{p}_{a}"
                rows.append((parent, post, label, author))
                for b, child_label in enumerate("ABCDEFGH"):
                    for j in range(1 + int((p + a + 2*b) % 3 == 0)):
                        child = f"t1_synthetic{p:03d}p{a}c{b}r{j}"
                        child_author = author if b == 0 else f"t2_synthetic_reply_author_{p}_{b}"
                        rows.append((child, parent, child_label, child_author))
            # Reverse each post's rows to exercise child-before-parent handling.
            for name, parent, label, author in reversed(rows):
                record = {"post_name": post, "comment_name": name, "parent_id": parent,
                          "subreddit": sub, "month": "2024-01", "label": label,
                          "author_fullname": author, "body": "Fictional software test record.",
                          "created_utc": 0, "coarse": "H" if label == "H" else "I",
                          "fine": None if label == "H" else label,
                          "synthetic": True}
                stream.write(json.dumps(record) + "\n")
                count += 1
    print(f"Wrote {count} fictional comments from 48 fictional discussions to {out}")

if __name__ == "__main__":
    main()
