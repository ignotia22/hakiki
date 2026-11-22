"""Ed25519 key generation, storage and fingerprints."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Union

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PathLike = Union[str, "os.PathLike[str]"]


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Return a new ``(private_key, public_key)`` pair."""
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def key_id(public_key: Ed25519PublicKey) -> str:
    """Short fingerprint: first 16 hex chars of SHA-256 over the raw public key."""
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def save_private_key(private_key: Ed25519PrivateKey, path: PathLike, overwrite: bool = False) -> None:
    """Write a PEM private key, readable only by the owner where the OS supports it."""
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    fd = os.open(path, flags | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - e.g. some Windows filesystems
        pass


def save_public_key(public_key: Ed25519PublicKey, path: PathLike, overwrite: bool = False) -> None:
    pem = public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(path, "wb" if overwrite else "xb") as f:
        f.write(pem)


def load_private_key(path: PathLike) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    return key


def load_public_key(path: PathLike) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path} is not an Ed25519 public key")
    return key


def as_private_key(key) -> Ed25519PrivateKey:
    """Accept a key object or a path to a PEM file."""
    if isinstance(key, Ed25519PrivateKey):
        return key
    if isinstance(key, (str, os.PathLike)):
        return load_private_key(key)
    raise TypeError("key must be an Ed25519PrivateKey or a path to a PEM file")


def as_public_key(key) -> Ed25519PublicKey:
    """Accept a public key object or a path to a PEM file."""
    if isinstance(key, Ed25519PublicKey):
        return key
    if isinstance(key, Ed25519PrivateKey):
        raise TypeError("verify needs the public key, not the private key")
    if isinstance(key, (str, os.PathLike)):
        return load_public_key(key)
    raise TypeError("public_key must be an Ed25519PublicKey or a path to a PEM file")
