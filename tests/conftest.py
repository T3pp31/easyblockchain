"""pytest 共通フィクスチャ。"""

import pytest

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pos import ProofOfStake
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import PosSettings, PowSettings


@pytest.fixture
def pos_setup():
    settings = PosSettings(min_stake=100, block_reward=10)
    validators = {
        "validator-a": 200,
        "validator-b": 300,
    }
    managers = {}
    instances = {}
    for vid in validators:
        sm = SignatureManager()
        sm.generate_key_pair()
        managers[vid] = sm
        pos = ProofOfStake(
            settings,
            node_validator_id=vid,
            signature_manager=sm,
            genesis_stakes=validators,
        )
        for v_id, stake in validators.items():
            pos.register_validator(v_id, stake)
        instances[vid] = pos
    return validators, managers, instances, settings


@pytest.fixture
def blockchain():
    return BlockChain()


@pytest.fixture
def pow_settings():
    return PowSettings(initial_difficulty=1, adjustment_interval=5, max_mining_iterations=500000)


@pytest.fixture
def pow_consensus(pow_settings):
    return ProofOfWork(pow_settings)


@pytest.fixture
def pow_blockchain(pow_consensus):
    return BlockChain(consensus=pow_consensus)


@pytest.fixture
def signature_manager():
    return SignatureManager()


@pytest.fixture
def signature_manager_with_keys():
    sig_manager = SignatureManager()
    sig_manager.generate_key_pair()
    return sig_manager


@pytest.fixture
def blockchain_factory():
    def _create_blockchain(enable_signature=True, with_keys=True):
        bc = BlockChain(enable_signature=enable_signature)
        if enable_signature and with_keys:
            bc.generate_key_pair()
        return bc

    return _create_blockchain


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: slow tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
