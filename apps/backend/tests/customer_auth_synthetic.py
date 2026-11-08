"""Deterministic, in-process identity providers for M4 Batch A tests only.

Neither adapter calls a provider or handles a real phone number. OTP codes and subjects are fixed synthetic fixtures.
"""
import time

from tests.customer_auth_support import claims, token


class SyntheticGoogleProvider:
    def __init__(self):
        self.issued_at = int(time.time())

    def issue(self, subject: str = "synthetic-google-subject") -> str:
        return token(payload=claims(sub=subject, iat=self.issued_at, nbf=self.issued_at - 5, exp=self.issued_at + 300))


class SyntheticPhoneOtpProvider:
    _codes = {"synthetic-phone-subject": "000111"}

    def __init__(self):
        self.issued_at = int(time.time())

    def exchange_otp(self, subject: str, code: str) -> str | None:
        if self._codes.get(subject) != code:
            return None
        return token(payload=claims(sub=subject, iat=self.issued_at, nbf=self.issued_at - 5, exp=self.issued_at + 300))
