import pytest

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pos import ProofOfStake, epoch_for_slot, validators_at_slot
from useful_blockchain.types import PosSettings
from pos_helpers import build_pos_chain


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


def test_compute_validators_from_chain_applies_rewards(pos_setup):
    # Given: genesis_stakes と報酬付きブロック1件
    # When: compute_validators_from_chain を呼ぶ
    # Then: 提案者のステークに block_reward が加算される
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    proposer = chain[0]["block_header"]["validator_id"]

    result = ProofOfStake.compute_validators_from_chain(
        chain, genesis_stakes, settings
    )
    assert result[proposer] == genesis_stakes[proposer] + settings.block_reward
    for vid, stake in genesis_stakes.items():
        if vid != proposer:
            assert result[vid] == stake


def test_compute_validators_from_chain_empty_chain(pos_setup):
    # Given: 空チェーン
    # When: compute_validators_from_chain を呼ぶ
    # Then: genesis_stakes と同一
    validators, _, _, settings = pos_setup
    genesis_stakes = dict(validators)
    result = ProofOfStake.compute_validators_from_chain([], genesis_stakes, settings)
    assert result == genesis_stakes


def test_validate_chain_with_genesis_stakes_accepts_valid_chain(pos_setup):
    # Given: 正しい PoS チェーン
    # When: validate_chain_with_genesis_stakes で検証
    # Then: True
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=3)
    pos = next(iter(instances.values()))
    assert pos.validate_chain_with_genesis_stakes(chain, genesis_stakes) is True


def test_validate_chain_with_genesis_stakes_rejects_wrong_proposer(pos_setup):
    # Given: 不正 proposer のブロックを含むチェーン
    # When: validate_chain_with_genesis_stakes で検証
    # Then: False
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    pos = next(iter(instances.values()))
    actual_proposer = chain[0]["block_header"]["validator_id"]
    wrong_proposer = (
        "validator-b" if actual_proposer == "validator-a" else "validator-a"
    )
    bad_block = dict(chain[0])
    bad_block["block_header"] = dict(chain[0]["block_header"])
    bad_block["block_header"]["validator_id"] = wrong_proposer
    assert pos.validate_chain_with_genesis_stakes([bad_block], genesis_stakes) is False


def test_sync_validators_from_chain_matches_compute(pos_setup):
    # Given: 複数ブロックのチェーン
    # When: sync_validators_from_chain を呼ぶ
    # Then: compute_validators_from_chain と一致
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=2)
    pos = instances["validator-a"]
    pos.sync_validators_from_chain(chain, genesis_stakes)
    expected = ProofOfStake.compute_validators_from_chain(
        chain, genesis_stakes, settings
    )
    assert pos.validators == expected


def test_epoch_for_slot():
    # Given: epoch_length=10
    # When: slot から epoch を計算
    # Then: エポック境界が期待どおり
    assert epoch_for_slot(1, 10) == 0
    assert epoch_for_slot(10, 10) == 0
    assert epoch_for_slot(11, 10) == 1


def test_validators_at_slot_uses_epoch_snapshot(pos_setup):
    # Given: epoch_length=3 の設定と1ブロック分の報酬
    # When: slot 2（同一エポック）のスナップショットを取得
    # Then: genesis_stakes のまま（エポック内報酬は反映されない）
    validators, _, instances, _ = pos_setup
    genesis_stakes = dict(validators)
    settings = PosSettings(epoch_length=3, min_stake=100, block_reward=10)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    snapshot = validators_at_slot(chain, genesis_stakes, settings, slot=2)
    assert snapshot == genesis_stakes


def test_validators_at_slot_updates_at_epoch_boundary(pos_setup):
    # Given: epoch_length=3 で3ブロック生成済み
    # When: slot 4（次エポック）のスナップショットを取得
    # Then: 直前エポックの報酬が反映される
    validators, _, instances, _ = pos_setup
    genesis_stakes = dict(validators)
    settings = PosSettings(epoch_length=3, min_stake=100, block_reward=10)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=3)
    snapshot = validators_at_slot(chain, genesis_stakes, settings, slot=4)
    expected = ProofOfStake.compute_validators_from_chain(chain, genesis_stakes, settings)
    assert snapshot == expected


def test_epoch_length_one_matches_live_stakes(pos_setup):
    # Given: epoch_length=1
    # When: slot 2 のスナップショットを取得
    # Then: 1ブロック目の報酬が反映される（従来挙動）
    validators, _, instances, _ = pos_setup
    genesis_stakes = dict(validators)
    settings = PosSettings(epoch_length=1, min_stake=100, block_reward=10)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    live = ProofOfStake.compute_validators_from_chain(chain, genesis_stakes, settings)
    snapshot = validators_at_slot(chain, genesis_stakes, settings, slot=2)
    assert snapshot == live


def test_validate_block_rejects_wrong_epoch(pos_setup):
    # Given: 正しいブロック
    # When: epoch ヘッダを改ざんして検証
    # Then: 拒否される
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    pos = next(iter(instances.values()))
    bad_block = dict(chain[0])
    bad_block["block_header"] = dict(chain[0]["block_header"])
    bad_block["block_header"]["epoch"] = 99
    result = pos.validate_block(
        bad_block,
        [],
        validators_at_state=validators_at_slot([], genesis_stakes, settings, 1),
    )
    assert result.valid is False
    assert result.reason == "epoch mismatch"


def test_select_canonical_chain_uses_genesis_stakes_for_validation(pos_setup):
    # Given: ローカルが遅れている PoS（validators は genesis のみ）
    # When: 長いチェーンを genesis_stakes 付きで比較
    # Then: 長いチェーンが正規として選ばれる
    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    long_chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=2)
    short_chain = long_chain[:1]
    pos = ProofOfStake(settings)
    pos.validators = dict(genesis_stakes)
    selected = pos.select_canonical_chain(
        [short_chain, long_chain], genesis_stakes=genesis_stakes
    )
    assert selected == long_chain
