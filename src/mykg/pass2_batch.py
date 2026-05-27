from __future__ import annotations

from mykg.chunker import Chunk


def build_pass2_batches(
    chunks: list[Chunk],
    batch_token_target: int,
    per_file: bool = False,
) -> list[list[Chunk]]:
    """Pack chunks into token-bounded batches for Pass 2.

    per_file=True: file boundaries are hard split points — chunks from different
    source files are never mixed in the same batch (mirrors pass1 per_file_batching).
    Chunks within a single large file may still span multiple batches.

    per_file=False (default): greedy sequential bin-packing across all files.
    """
    if per_file:
        batches: list[list[Chunk]] = []
        current: list[Chunk] = []
        current_tokens = 0
        current_file: str | None = None
        for chunk in chunks:
            size = chunk.token_end - chunk.token_start
            file_changed = current_file is not None and chunk.source_file != current_file
            token_overflow = current and current_tokens + size > batch_token_target
            if file_changed or token_overflow:
                batches.append(current)
                current = []
                current_tokens = 0
            current.append(chunk)
            current_tokens += size
            current_file = chunk.source_file
        if current:
            batches.append(current)
        return batches

    batches = []
    current = []
    current_tokens = 0
    for chunk in chunks:
        size = chunk.token_end - chunk.token_start
        if current and current_tokens + size > batch_token_target:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += size
    if current:
        batches.append(current)
    return batches


def make_batch_map(batches: list[list[Chunk]]) -> dict[str, dict]:
    """Return {batch_name: entry} for pass2_batch_map.json.

    Each entry has:
      - "files": sorted unique list of source_file values in this batch
      - "chunks": list of {"file": source_file, "chunk_idx": chunk_index} (1-based)
      - "total_tokens": sum of (token_end - token_start) for all chunks
    """
    result: dict[str, dict] = {}
    for i, batch in enumerate(batches):
        name = f"batch_{i:04d}"
        files = sorted({c.source_file for c in batch})
        chunks = [{"file": c.source_file, "chunk_idx": c.chunk_index + 1} for c in batch]
        total = sum(c.token_end - c.token_start for c in batch)
        result[name] = {"files": files, "chunks": chunks, "total_tokens": total}
    return result
