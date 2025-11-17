"""
RPC client tests using a mocked Web3 instance.

These verify the client's own logic (unit conversion, transaction
construction, receipt parsing) without depending on a live testnet
connection — appropriate for CI. See README for how to smoke-test against
a real Sepolia endpoint manually.
"""
from unittest.mock import MagicMock, patch

import pytest

from wallet_rpc.chains import SEPOLIA
from wallet_rpc.rpc_client import RPCClient


@pytest.fixture
def client_with_mocked_web3():
    with patch("wallet_rpc.rpc_client.Web3") as MockWeb3Class:
        mock_w3_instance = MagicMock()
        MockWeb3Class.return_value = mock_w3_instance
        MockWeb3Class.HTTPProvider = MagicMock()
        MockWeb3Class.to_checksum_address = staticmethod(lambda addr: addr)

        client = RPCClient(SEPOLIA, "http://fake-rpc-endpoint")
        yield client, mock_w3_instance


def test_get_native_balance_converts_wei_to_ether(client_with_mocked_web3):
    client, mock_w3 = client_with_mocked_web3
    mock_w3.eth.get_balance.return_value = 1_500_000_000_000_000_000  # 1.5 ETH in wei
    mock_w3.from_wei.return_value = 1.5

    balance = client.get_native_balance("0xSomeAddress")

    assert balance == 1.5
    mock_w3.eth.get_balance.assert_called_once()


def test_build_transfer_transaction_has_expected_fields(client_with_mocked_web3):
    client, mock_w3 = client_with_mocked_web3
    mock_w3.eth.get_transaction_count.return_value = 5
    mock_w3.to_wei.return_value = 1_000_000_000_000_000
    mock_w3.eth.gas_price = 20_000_000_000

    tx = client.build_transfer_transaction("0xFrom", "0xTo", 0.001)

    assert tx["chainId"] == SEPOLIA.chain_id
    assert tx["nonce"] == 5
    assert tx["gas"] == 21_000
    assert tx["value"] == 1_000_000_000_000_000


def test_wait_for_confirmation_parses_successful_receipt(client_with_mocked_web3):
    client, mock_w3 = client_with_mocked_web3
    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_receipt.blockNumber = 12345
    mock_receipt.gasUsed = 21000
    mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

    summary = client.wait_for_confirmation("0xabc123")

    assert summary.status == "success"
    assert summary.block_number == 12345
    assert summary.gas_used == 21000


def test_wait_for_confirmation_parses_failed_receipt(client_with_mocked_web3):
    client, mock_w3 = client_with_mocked_web3
    mock_receipt = MagicMock()
    mock_receipt.status = 0
    mock_receipt.blockNumber = 999
    mock_receipt.gasUsed = 21000
    mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

    summary = client.wait_for_confirmation("0xabc123")

    assert summary.status == "failed"


def test_broadcast_signed_transaction_returns_hex_hash(client_with_mocked_web3):
    client, mock_w3 = client_with_mocked_web3
    mock_tx_hash = MagicMock()
    mock_tx_hash.hex.return_value = "0xdeadbeef"
    mock_w3.eth.send_raw_transaction.return_value = mock_tx_hash

    mock_signed_tx = MagicMock()
    mock_signed_tx.raw_transaction = b"fake-raw-tx-bytes"

    result = client.broadcast_signed_transaction(mock_signed_tx)

    assert result == "0xdeadbeef"
