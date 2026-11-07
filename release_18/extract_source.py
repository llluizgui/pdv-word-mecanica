"""Restores reviewed 1.8 source and verifies SHA-256 before running any code."""
import base64
import hashlib
import lzma
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sources = (
    ("workflow_v18.py", [f"release_18/workflow_v18_part{i}.xz64" for i in range(1, 5)], "71671e9bcf16d6c49f304526696c30e693c3489e33680b34e594b966e42e07d1"),
    ("test_v18.py", ["release_18/test_v18.xz64"], "b56bfe43a15e14edafc990c0ea728de0ae862f816e6e60e49babb2d988be10bb"),
)
for filename, paths, expected_sha in sources:
    encoded = "".join((root / path).read_text(encoding="ascii").strip() for path in paths)
    contents = lzma.decompress(base64.b64decode(encoded, validate=True))
    actual_sha = hashlib.sha256(contents).hexdigest()
    if actual_sha != expected_sha:
        raise RuntimeError(f"Invalid SHA-256 for {filename}: got {actual_sha}, expected {expected_sha}")
    (root / filename).write_bytes(contents)
    print(f"Extracted and verified {filename} ({len(contents)} bytes) SHA-256={actual_sha}")
