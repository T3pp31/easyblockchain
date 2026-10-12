from useful_blockchain.consensus.factory import create_consensus
from useful_blockchain.types import AppSettings, ConsensusSettings, PosSettings


def test_create_consensus_does_not_mutate_genesis_stakes():
    # Given: 呼び出し元が所有する genesis_stakes（node_validator_id を含まない）
    # When: create_consensus に渡す
    # Then: 呼び出し元の辞書は変更されない
    settings = AppSettings(
        consensus=ConsensusSettings(type="pos", pos=PosSettings(min_stake=100))
    )
    genesis_stakes = {"validator-a": 200}

    create_consensus(settings, node_validator_id="validator-b", genesis_stakes=genesis_stakes)

    assert genesis_stakes == {"validator-a": 200}
