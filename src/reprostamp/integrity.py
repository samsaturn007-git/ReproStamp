import hashlib
import json
from typing import BinaryIO


def canonical_json(value: object) -> bytes:
    """RFC 8785 serialization for the receipt schema's integer-only JSON values."""

    def encode(item: object) -> str:
        if isinstance(item, dict):
            keys = sorted(item, key=lambda key: key.encode("utf-16-be"))
            return "{" + ",".join(f"{encode(key)}:{encode(item[key])}" for key in keys) + "}"
        if isinstance(item, (list, tuple)):
            return "[" + ",".join(map(encode, item)) + "]"
        if type(item) is int and abs(item) >= 2**53:
            raise ValueError("Receipt integers must fit in the JSON safe integer range.")
        if item is None or isinstance(item, (bool, int, str)):
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        raise ValueError("Receipt JSON accepts only integer numbers.")

    return encode(value).encode("utf-8")


def hash_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def hash_file(file: BinaryIO) -> str:
    return hashlib.file_digest(file, "sha256").hexdigest()
