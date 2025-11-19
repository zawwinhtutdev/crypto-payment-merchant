import pytest

from app.ledger import Ledger, InsufficientFundsError, WalletNotFoundError


@pytest.fixture
def ledger():
    return Ledger()


def test_transfer_moves_balance(ledger):
    a = ledger.create_wallet("alice", "USD", opening_balance=100)
    b = ledger.create_wallet("bob", "USD", opening_balance=0)

    entry, was_duplicate = ledger.post_transfer(a.wallet_id, b.wallet_id, 40, "USD", "key-1")

    assert was_duplicate is False
    assert entry.status == "settled"
    assert ledger.get_wallet(a.wallet_id).balance == 60
    assert ledger.get_wallet(b.wallet_id).balance == 40


def test_idempotency_key_prevents_double_processing(ledger):
    a = ledger.create_wallet("alice", "USD", opening_balance=100)
    b = ledger.create_wallet("bob", "USD", opening_balance=0)

    ledger.post_transfer(a.wallet_id, b.wallet_id, 40, "USD", "same-key")
    entry2, was_duplicate = ledger.post_transfer(a.wallet_id, b.wallet_id, 40, "USD", "same-key")

    assert was_duplicate is True
    # Balance must NOT be debited twice — this is the core guarantee.
    assert ledger.get_wallet(a.wallet_id).balance == 60
    assert ledger.get_wallet(b.wallet_id).balance == 40


def test_insufficient_funds_raises(ledger):
    a = ledger.create_wallet("alice", "USD", opening_balance=10)
    b = ledger.create_wallet("bob", "USD", opening_balance=0)

    with pytest.raises(InsufficientFundsError):
        ledger.post_transfer(a.wallet_id, b.wallet_id, 500, "USD", "key-2")

    # Failed attempt must not have moved any funds.
    assert ledger.get_wallet(a.wallet_id).balance == 10
    assert ledger.get_wallet(b.wallet_id).balance == 0


def test_unknown_wallet_raises(ledger):
    a = ledger.create_wallet("alice", "USD", opening_balance=10)
    with pytest.raises(WalletNotFoundError):
        ledger.post_transfer(a.wallet_id, "does-not-exist", 5, "USD", "key-3")


def test_currency_mismatch_fails_gracefully(ledger):
    a = ledger.create_wallet("alice", "USD", opening_balance=100)
    b = ledger.create_wallet("bob", "USDC", opening_balance=0)

    entry, was_duplicate = ledger.post_transfer(a.wallet_id, b.wallet_id, 10, "USD", "key-4")

    assert was_duplicate is False
    assert entry.status == "failed"
    assert ledger.get_wallet(a.wallet_id).balance == 100  # untouched
