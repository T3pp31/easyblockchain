import pytest

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pos import ProofOfStake
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import PosSettings


@pytest.fixture
def pos_setup():
    settings = PosSettings(min_stake=100, block_reward=10)
    validators = {
        "validator-a": 200,
        "validator-b": 300,
    }
    managers = {}
    consensus_instances = {}
    for vid in validators:
        sm = SignatureManager()
        sm.generate_key_pair()
        managers[vid] = sm
        pos = ProofOfStake(settings, node_validator_id=vid, signature_manager=sm)
        for v_id, stake in validators.items():
            pos.register_validator(v_id, stake)
        consensus_instances[vid] = pos
    return validators, managers, consensus_instances, settings


def test_proposer_rotation(pos_setup):
    _, _, instances, _ = pos_setup
    pos = next(iter(instances.values()))
    proposers = {pos.select_proposer(slot) for slot in range(1, 20)}
    assert len(proposers) >= 2


def test_only_proposer_can_prepare(pos_setup):
    _, _, instances, _ = pos_setup
    proposer_id = "validator-a"
    pos_a = instances[proposer_id]
    bc = BlockChain(enable_signature=True, consensus=pos_a)
    slot1_proposer = pos_a.select_proposer(1)
    if slot1_proposer == proposer_id:
        block = bc.add_new_block(["x"], ["y"])
        assert block["block_header"]["validator_id"] == proposer_id
    else:
        with pytest.raises(ValueError, match="Not proposer"):
            bc.add_new_block(["x"], ["y"])


def test_stake_reward_on_block_added(pos_setup):
    _, _, instances, settings = pos_setup
    pos = instances["validator-a"]
    initial = pos.validators["validator-a"]
    block = {
        "block_header": {"validator_id": "validator-a"},
        "block_index": 1,
    }
    pos.on_block_added(block)
    assert pos.validators["validator-a"] == initial + settings.block_reward


def test_reject_unknown_validator(pos_setup):
    _, _, instances, _ = pos_setup
    pos = next(iter(instances.values()))
    fake_block = {
        "block_index": 1,
        "block_item": "2024-01-01 00:00:00",
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "f" * 64,
            "consensus_type": "pos",
            "validator_id": "unknown",
            "slot": 1,
        },
        "tran_body": {"input_data": ["a"], "output_data": ["b"]},
        "tran_counter": 2,
        "signature": "00",
        "public_key": "invalid",
    }
    result = pos.validate_block(fake_block, [])
    assert result.valid is False
