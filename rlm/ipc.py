"""Length-prefixed JSON framing for the host ↔ container channel."""

from __future__ import annotations

import json
from typing import Any, Protocol


class ByteStream(Protocol):
    def recv(self, n: int) -> bytes: ...
    def sendall(self, data: bytes) -> None: ...


class FileStream(Protocol):
    def read(self, n: int) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def flush(self) -> None: ...


MAX_MESSAGE_BYTES = 32_000_000


def _read_exact(stream: Any, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        remaining = n - len(buf)
        if hasattr(stream, "recv"):
            chunk = stream.recv(remaining)
        else:
            chunk = stream.read(remaining)
        if not chunk:
            raise ConnectionError("stream closed while reading")
        buf.extend(chunk)
    return bytes(buf)


def _write_all(stream: Any, data: bytes) -> None:
    if hasattr(stream, "sendall"):
        stream.sendall(data)
        return
    stream.write(data)
    stream.flush()


def write_msg(stream: Any, obj: dict[str, Any]) -> None:
    payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    header = len(payload).to_bytes(4, "big")
    _write_all(stream, header + payload)


def read_msg(stream: Any) -> dict[str, Any]:
    header = _read_exact(stream, 4)
    n = int.from_bytes(header, "big")
    if n > MAX_MESSAGE_BYTES:
        raise ValueError(f"message too large: {n} bytes")
    payload = _read_exact(stream, n)
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("message must be a JSON object")
    return data
