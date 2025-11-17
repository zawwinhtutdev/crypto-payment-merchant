"""
Wallet tests — pure local crypto operations, no network needed.
"""
from wallet_rpc.wallet import Wallet


def test_create_generates_valid_address():
    wallet = Wallet.create()
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42  # 0x + 40 hex chars


def test_create_generates_unique_wallets():
    w1 = Wallet.create()
    w2 = Wallet.create()
    assert w1.address != w2.address


def test_from_private_key_recovers_same_address():
    original = Wallet.create()
    private_key = original.export_private_key_HEX_DANGEROUS()

    restored = Wallet.from_private_key(private_key)

    assert restored.address == original.address


def test_sign_message_is_deterministic():
    wallet = Wallet.create()
    sig1 = wallet.sign_message("hello mesh")
    sig2 = wallet.sign_message("hello mesh")
    assert sig1 == sig2


def test_sign_message_differs_per_message():
    wallet = Wallet.create()
    sig1 = wallet.sign_message("message A")
    sig2 = wallet.sign_message("message B")
    assert sig1 != sig2


def test_sign_transaction_produces_raw_bytes():
    wallet = Wallet.create()
    tx = {
        "chainId": 11155111,
        "to": Wallet.create().address,
        "value": 1_000_000_000_000_000,  # 0.001 ETH in wei
        "nonce": 0,
        "gas": 21000,
        "gasPrice": 20_000_000_000,
    }
    signed = wallet.sign_transaction(tx)
    assert signed.raw_transaction is not None
    assert len(signed.raw_transaction) > 0
