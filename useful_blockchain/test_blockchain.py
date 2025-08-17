import pytest

from useful_blockchain.blockchain import BlockChain


@pytest.fixture
def blockchain():
    return BlockChain()

def test_add_new_block(blockchain):
    block1 = blockchain.add_new_block("input1", "output1")
    block2 = blockchain.add_new_block("input2", "output2")

    assert len(blockchain.chain) == 2
    assert block1["block_index"] == 1
    assert block2["block_index"] == 2

def test_calc_tran_hash(blockchain):
    input_data = "test_input"
    output_data = "test_output"
    new_transaction = blockchain._BlockChain__create_new_transaction(input_data, output_data)
    calculated_hash = blockchain._BlockChain__calc_tran_hash(new_transaction)

    # Manually calculate the expected hash from the transaction data
    import json
    import hashlib
    tran_string = json.dumps(new_transaction, sort_keys=True).encode()
    expected_hash = hashlib.sha256(str(tran_string).encode()).hexdigest()

    assert calculated_hash == expected_hash
