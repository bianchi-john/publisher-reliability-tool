"""Remember which local checkpoints were already verified, so restarts stay fast.

Verifying one checkpoint means reading every byte of it twice: once for the SHA-256
that is its scientific identity, and once for the strict-shape ``torch.load`` that
proves the file really is the expected classifier. For the paper's five BERT and
five RoBERTa folds that is roughly 8.8 GB and about a minute on every start, even
when nothing on disk has changed.

This cache stores the outcome of a *successful* verification next to a fingerprint
of the file it came from: device, inode, size and modification time in nanoseconds.
If any part of that fingerprint differs the checkpoint is verified again from
scratch, and a rejected checkpoint is never remembered, so a broken file keeps
being reported on every scan.

The whole cache is discarded whenever the validation rules change, so a check that
is tightened later can never be skipped because of an entry written under the older,
weaker rules.

The cache can only ever save work, never create it: deleting the file, or passing
``--full`` to ``publisher-reliability models scan``, forces complete verification
again. That is why it lives beside the ledgers rather than inside ``state/``, which
holds only the six authoritative CSVs.

What it gives up, honestly: a cache hit asserts that the file has not been touched
since it was verified, not that its bytes were re-read now. It does not lower the
bar against a local attacker, who would need write access to the model directory and
could rewrite this file just as easily. What is no longer detected automatically is
silent corruption that leaves size and timestamp untouched, such as bit rot on a
failing disk; ``models scan --full`` is the answer when that matters.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CACHE_FILENAME = "model-scan-cache.json"

# Bump when the *structure* of a cache entry changes. Changes to what validation
# actually checks are covered by the rules fingerprint instead, which the scanner
# derives from the rules themselves.
CACHE_FORMAT_VERSION = 1


def file_fingerprint(path: Path) -> dict[str, int]:
    """Identify a file well enough to tell "untouched" from "possibly different".

    Inode and device are included alongside size and timestamp so that replacing a
    checkpoint with a different file of the same size, or restoring an old copy over
    it, does not look unchanged.
    """

    stat = path.stat()
    return {
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


class ScanCache:
    """Verification results from previous scans, keyed by absolute file path."""

    def __init__(self, path: Path, rules_fingerprint: str):
        self.path = path
        self.rules_fingerprint = rules_fingerprint
        self.entries = self._load()

    def _load(self) -> dict[str, dict]:
        """Read the cache, treating anything unreadable or stale as simply absent.

        A damaged cache must never stop the application from starting: the only cost
        of discarding it is that this scan verifies everything again.
        """

        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(document, dict):
            return {}
        if document.get("cache_format_version") != CACHE_FORMAT_VERSION:
            return {}
        if document.get("rules_fingerprint") != self.rules_fingerprint:
            return {}
        entries = document.get("entries")
        return entries if isinstance(entries, dict) else {}

    def lookup(self, path: Path) -> dict | None:
        """Return the stored verification for `path`, or None if it must be redone."""

        entry = self.entries.get(str(path))
        if entry is None:
            return None
        try:
            current = file_fingerprint(path)
        except OSError:
            return None
        if entry.get("fingerprint") != current:
            return None
        return entry.get("result")

    def remember(self, path: Path, result: dict[str, object]) -> None:
        """Record a successful verification so the next scan can skip this file."""

        try:
            fingerprint = file_fingerprint(path)
        except OSError:
            return
        self.entries[str(path)] = {"fingerprint": fingerprint, "result": result}

    def save(self) -> None:
        """Write the cache atomically, dropping entries whose file has disappeared.

        Written to a temporary file and renamed so a crash leaves either the previous
        cache or the new one, never a truncated file that the next start would have to
        throw away. Failure to write is ignored: the cache is an optimisation, and a
        workspace that cannot be written has already failed louder elsewhere.
        """

        live = {key: entry for key, entry in self.entries.items() if Path(key).exists()}
        document = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "rules_fingerprint": self.rules_fingerprint,
            "entries": live,
        }
        temporary = self.path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(document, indent=1, sort_keys=True), encoding="utf-8"
            )
            os.replace(temporary, self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
