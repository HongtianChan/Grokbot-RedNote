#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Encrypt local Application Support JSON/JSONL files at rest.

Python's standard library has no AES implementation, so AES-256-CBC is
done through macOS CommonCrypto via ctypes (no pip packages). The key is
derived with PBKDF2-HMAC-SHA256 (stdlib) from this machine's hardware
UUID, or the hostname if that is unavailable.

File format: b"GRNE1" + IV (16) + ciphertext + HMAC-SHA256 (32).
Plaintext JSON/JSONL already on disk is accepted on read and rewritten
encrypted on the next write. Missing or corrupt files raise CorruptFile
so callers can recreate defaults.
"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

MAGIC = b"GRNE1"
IV_LEN = 16
MAC_LEN = 32
_PBKDF2_ROUNDS = 100_000
_SALT = b"grokbot-rednote-at-rest-v1"

# CommonCrypto
_kCCEncrypt = 0
_kCCDecrypt = 1
_kCCAlgorithmAES = 0
_kCCOptionPKCS7Padding = 1
_kCCSuccess = 0

_KEYS: Optional[tuple[bytes, bytes]] = None
_CCCRYPT = None


class CorruptFile(ValueError):
    """The file exists but cannot be decrypted or parsed."""


def _hardware_identity() -> str:
    try:
        result = subprocess.run(
            ["/usr/sbin/ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return socket.gethostname() or "unknown-host"


def machine_material() -> bytes:
    raw = _hardware_identity().encode("utf-8")
    return hashlib.sha256(b"grokbot-rednote-machine:" + raw).digest()


def derived_keys() -> tuple[bytes, bytes]:
    """Return (aes_key_32, mac_key_32), cached for this process."""
    global _KEYS
    if _KEYS is None:
        material = machine_material()
        out = hashlib.pbkdf2_hmac("sha256", material, _SALT, _PBKDF2_ROUNDS, dklen=64)
        _KEYS = (out[:32], out[32:])
    return _KEYS


def reset_keys_for_tests() -> None:
    global _KEYS
    _KEYS = None


def _ccrypt():
    global _CCCRYPT
    if _CCCRYPT is not None:
        return _CCCRYPT
    lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
    fn = lib.CCCrypt
    fn.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    fn.restype = ctypes.c_int32
    _CCCRYPT = fn
    return fn


def _aes_cbc(op: int, key: bytes, iv: bytes, data: bytes) -> bytes:
    fn = _ccrypt()
    buf = ctypes.create_string_buffer(len(data) + 16)
    moved = ctypes.c_size_t(0)
    status = fn(
        op,
        _kCCAlgorithmAES,
        _kCCOptionPKCS7Padding,
        key,
        len(key),
        iv,
        data,
        len(data),
        buf,
        len(buf),
        ctypes.byref(moved),
    )
    if status != _kCCSuccess:
        raise CorruptFile("AES operation failed (%s)" % status)
    return buf.raw[: moved.value]


def encrypt_bytes(plain: bytes) -> bytes:
    aes_key, mac_key = derived_keys()
    iv = os.urandom(IV_LEN)
    cipher = _aes_cbc(_kCCEncrypt, aes_key, iv, plain)
    digest = hmac.new(mac_key, iv + cipher, hashlib.sha256).digest()
    return MAGIC + iv + cipher + digest


def _looks_plaintext(data: bytes) -> bool:
    if not data:
        return True
    stripped = data.lstrip()
    if stripped.startswith(MAGIC):
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lead = text.lstrip()
    return (not lead) or lead[0] in "{[" or lead.startswith("//")


def decrypt_bytes(data: bytes) -> bytes:
    if _looks_plaintext(data):
        return data
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + IV_LEN + MAC_LEN + 16:
        raise CorruptFile("Not a Grokbot-RedNote encrypted file")
    body = data[len(MAGIC) :]
    iv = body[:IV_LEN]
    digest = body[-MAC_LEN:]
    cipher = body[IV_LEN:-MAC_LEN]
    aes_key, mac_key = derived_keys()
    expected = hmac.new(mac_key, iv + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(digest, expected):
        raise CorruptFile("File integrity check failed")
    return _aes_cbc(_kCCDecrypt, aes_key, iv, cipher)


def is_encrypted_blob(data: bytes) -> bool:
    return data.startswith(MAGIC)


def read_bytes(path: Path) -> Optional[bytes]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    try:
        return decrypt_bytes(data)
    except CorruptFile:
        _quarantine(path)
        return None


def write_bytes(path: Path, plain: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = encrypt_bytes(plain)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def read_text(path: Path, default: str = "") -> str:
    data = read_bytes(path)
    if data is None:
        return default
    return data.decode("utf-8")


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    text = read_text(path, default="")
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _quarantine(path)
        return default


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _quarantine(path: Path) -> None:
    path = Path(path)
    if not path.is_file():
        return
    dest = path.with_suffix(path.suffix + ".corrupt")
    try:
        if dest.exists():
            dest.unlink()
        path.replace(dest)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass


def migrate_file(path: Path) -> str:
    """Encrypt a plaintext file in place. Missing or already encrypted: leave it.

    Returns 'encrypted', 'already', 'missing', or 'corrupt'.
    """
    path = Path(path)
    if not path.is_file():
        return "missing"
    try:
        data = path.read_bytes()
    except OSError:
        return "missing"
    if is_encrypted_blob(data):
        try:
            decrypt_bytes(data)
        except CorruptFile:
            _quarantine(path)
            return "corrupt"
        return "already"
    if not _looks_plaintext(data):
        _quarantine(path)
        return "corrupt"
    try:
        write_bytes(path, data)
    except Exception:
        return "corrupt"
    return "encrypted"


KNOWN_DATA_FILES = (
    "learn.jsonl",
    "learn.jsonl.bak",
    "weights.json",
    "weights.json.bak",
    "settings.json",
    "state.json",
    "subscription.json",
    "subscription.key",
)


def migrate_state_dir(
    state_dir: Optional[Path] = None,
    shadow_file: Optional[Path] = None,
) -> dict[str, str]:
    root = Path(state_dir or (Path.home() / "Library" / "Application Support" / "Grokbot-RedNote"))
    report: dict[str, str] = {}
    for name in KNOWN_DATA_FILES:
        report[name] = migrate_file(root / name)
    if shadow_file is not None:
        report[str(shadow_file)] = migrate_file(Path(shadow_file))
    else:
        cache = Path.home() / "Library" / "Caches" / "Grokbot-RedNote" / "usage.json"
        report["usage.json"] = migrate_file(cache)
    return report
