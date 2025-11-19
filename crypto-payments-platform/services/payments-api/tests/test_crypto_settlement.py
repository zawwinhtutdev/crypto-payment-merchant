import pytest

from app.crypto_settlement import (
    BlockchainRPCClient,
    SelfCustodyWallet,
    StablecoinSettlementService,
    TxStatus,
)


def test_self_custody_wallet_generates_unique_addresses():
    w1 = SelfCustodyWallet.create()
    w2 = SelfCustodyWallet.create()
    assert w1.address != w2.address
    assert w1.address.startswith("0x")


def test_wallet_signature_is_deterministic_for_same_message():
    wallet = SelfCustodyWallet.create()
    sig1 = wallet.sign("transfer:100:USDC")
    sig2 = wallet.sign("transfer:100:USDC")
    assert sig1 == sig2  # same key + same message -> same signature


def test_rpc_broadcast_and_confirm():
    rpc = BlockchainRPCClient()
    wallet = SelfCustodyWallet.create()
    sig = wallet.sign("test-tx")
    tx_hash = rpc.broadcast_transaction(wallet.address, "0xmerchant", 50.0, sig)
    assert rpc.get_transaction_status(tx_hash) == TxStatus.CONFIRMED


def test_unknown_tx_hash_reports_failed():
    rpc = BlockchainRPCClient()
    assert rpc.get_transaction_status("0xdoesnotexist") == TxStatus.FAILED


def test_stablecoin_settlement_converts_to_fiat():
    rpc = BlockchainRPCClient()
    service = StablecoinSettlementService(rpc)
    wallet = SelfCustodyWallet.create()

    result = service.settle_to_fiat(wallet, "0xmerchant", "USDC", 125.50)

    assert result["settled_fiat_currency"] == "USD"
    assert result["settled_fiat_amount"] == 125.50
    assert result["chain_status"] == "confirmed"
    assert result["tx_hash"].startswith("0x")


def test_unsupported_stablecoin_rejected():
    rpc = BlockchainRPCClient()
    service = StablecoinSettlementService(rpc)
    wallet = SelfCustodyWallet.create()

    with pytest.raises(ValueError):
        service.settle_to_fiat(wallet, "0xmerchant", "DOGE", 10)
