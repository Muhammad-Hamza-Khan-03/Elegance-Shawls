"""Encrypt-then-MAC for backup archives using the standard `openssl` CLI plus stdlib HMAC.

The archive is AES-256-CBC (PBKDF2, random salt). Authenticity comes from an HMAC-SHA256 over the manifest, which carries the
SHA-256 of the ciphertext, so a wrong passphrase, corruption or tampering is rejected *before* anything is decrypted.
The passphrase is handed to openssl over a pipe (never argv or the environment) and never appears in errors.
"""
import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path

KDF_ITER = 600_000
MIN_KDF_ITER, MAX_KDF_ITER = 100_000, 5_000_000  # the manifest is untrusted input: bound the work it can request
MIN_PASSPHRASE_CHARS = 32


class CryptoError(Exception):
    pass


def check_passphrase(passphrase: str) -> str:
    if len(passphrase) < MIN_PASSPHRASE_CHARS or passphrase.startswith("replace-with"):
        raise CryptoError(f"encryption passphrase must be a generated secret of at least {MIN_PASSPHRASE_CHARS} characters")
    return passphrase


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _openssl(mode: str, src: Path, dst: Path, passphrase: str, iterations: int) -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, passphrase.encode())  # far below the pipe buffer, so this cannot block
    os.close(write_fd)
    try:
        proc = subprocess.run(
            ["openssl", "enc", mode, "-aes-256-cbc", "-pbkdf2", "-iter", str(iterations), "-salt",
             "-pass", f"fd:{read_fd}", "-in", str(src), "-out", str(dst)],
            pass_fds=(read_fd,), capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CryptoError("openssl is not installed") from exc
    finally:
        os.close(read_fd)
    if proc.returncode != 0:
        dst.unlink(missing_ok=True)
        raise CryptoError(f"openssl {mode} failed (exit {proc.returncode})")


def _mac(manifest: dict, passphrase: str) -> str:
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), bytes.fromhex(manifest["mac_salt"]), manifest["kdf_iter"], 32)
    body = json.dumps({k: v for k, v in manifest.items() if k != "mac"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def encrypt_file(plain: Path, cipher: Path, passphrase: str, manifest: dict) -> dict:
    """Encrypts `plain` to `cipher` and returns `manifest` extended with sizes, digests, KDF parameters and the MAC."""
    check_passphrase(passphrase)
    _openssl("-e", plain, cipher, passphrase, KDF_ITER)
    signed = {**manifest, "cipher": "aes-256-cbc-pbkdf2", "kdf_iter": KDF_ITER, "mac_salt": os.urandom(16).hex(),
              "plaintext_sha256": sha256_file(plain), "ciphertext_sha256": sha256_file(cipher),
              "ciphertext_bytes": cipher.stat().st_size}
    return {**signed, "mac": _mac(signed, passphrase)}


def verify_manifest(manifest: dict, cipher: Path, passphrase: str) -> None:
    """Raises CryptoError unless the MAC and the ciphertext digest both match. Does not decrypt."""
    check_passphrase(passphrase)
    try:
        if not MIN_KDF_ITER <= manifest["kdf_iter"] <= MAX_KDF_ITER:
            raise CryptoError("manifest requests an unreasonable KDF iteration count")
        expected = _mac(manifest, passphrase)
        if not hmac.compare_digest(expected, str(manifest["mac"])):
            raise CryptoError("manifest authentication failed: wrong passphrase or tampered manifest")
        if cipher.stat().st_size != manifest["ciphertext_bytes"] or sha256_file(cipher) != manifest["ciphertext_sha256"]:
            raise CryptoError("ciphertext integrity check failed: archive is corrupt or truncated")
    except (KeyError, TypeError, ValueError) as exc:
        raise CryptoError("manifest is malformed") from exc


def decrypt_file(cipher: Path, plain: Path, passphrase: str, manifest: dict) -> None:
    """Verifies, decrypts and checks the plaintext digest; removes `plain` on any failure."""
    verify_manifest(manifest, cipher, passphrase)
    _openssl("-d", cipher, plain, passphrase, manifest["kdf_iter"])
    if sha256_file(plain) != manifest["plaintext_sha256"]:
        plain.unlink(missing_ok=True)
        raise CryptoError("decrypted archive does not match the recorded plaintext digest")
