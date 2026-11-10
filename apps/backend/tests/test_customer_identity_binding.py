"""Issuer and subject remain distinct from provider labels and anonymous session ids."""
from repositories.customer_auth import exchange_key_hash, identity_subject_key
from tests.customer_auth_synthetic import SyntheticGoogleProvider, SyntheticPhoneOtpProvider


def test_verified_issuer_is_bound_to_subject_without_storing_bare_subject():
    first = identity_subject_key("https://idp.test.invalid", "synthetic-subject")
    assert len(first) == 64 and "synthetic-subject" not in first
    assert first == identity_subject_key("https://idp.test.invalid", "synthetic-subject")
    assert first != identity_subject_key("https://other.test.invalid", "synthetic-subject")
    assert first != identity_subject_key("https://idp.test.invalid", "another-subject")


def test_exchange_replay_key_is_bound_to_issuer_subject_and_explicit_key():
    key = exchange_key_hash("issuer", "subject", "idem_syntheticlogin01")
    assert key != exchange_key_hash("other-issuer", "subject", "idem_syntheticlogin01")
    assert key != exchange_key_hash("issuer", "other-subject", "idem_syntheticlogin01")
    assert key != exchange_key_hash("issuer", "subject", "idem_syntheticlogin02")


def test_synthetic_provider_adapters_are_deterministic_and_phone_otp_is_bounded():
    google = SyntheticGoogleProvider()
    phone = SyntheticPhoneOtpProvider()
    assert google.issue() == google.issue()
    assert phone.exchange_otp("synthetic-phone-subject", "000111") == phone.exchange_otp("synthetic-phone-subject", "000111")
    assert phone.exchange_otp("synthetic-phone-subject", "bad") is None
    assert phone.exchange_otp("unknown-subject", "000111") is None
