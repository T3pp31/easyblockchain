"""
pytest設定ファイル

プロジェクト全体で使用される共通のfixtureと設定を定義します。
"""

import pytest
import sys
import os

# パッケージをインポートするためのパス設定
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from useful_blockchain.signature import SignatureManager
from useful_blockchain.blockchain import BlockChain


@pytest.fixture(scope="session")
def test_key_pair():
    """
    テストセッション全体で使用する鍵ペアを生成するfixture
    
    Returns:
        tuple: (private_key, public_key)
    """
    sig_manager = SignatureManager()
    return sig_manager.generate_key_pair()


@pytest.fixture
def sample_transaction_data():
    """
    サンプル取引データのfixture
    
    Returns:
        dict: 取引データの辞書
    """
    return {
        "from": "Alice",
        "to": "Bob", 
        "amount": 100,
        "timestamp": "2023-01-01T12:00:00Z",
        "transaction_id": "tx_001"
    }


@pytest.fixture
def sample_block_data():
    """
    サンプルブロックデータのfixture
    
    Returns:
        dict: ブロックデータの辞書
    """
    return {
        "block_index": 1,
        "timestamp": "2023-01-01T12:00:00Z",
        "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
        "transactions": [
            {"from": "Alice", "to": "Bob", "amount": 50},
            {"from": "Bob", "to": "Charlie", "amount": 30}
        ]
    }


@pytest.fixture(params=[1024, 2048])
def signature_manager_various_key_sizes(request):
    """
    異なる鍵サイズのSignatureManagerを作成するparametrized fixture
    
    Args:
        request: pytestのrequest fixture
        
    Returns:
        SignatureManager: 指定された鍵サイズで初期化されたSignatureManager
    """
    sig_manager = SignatureManager()
    sig_manager.generate_key_pair(request.param)
    return sig_manager


@pytest.fixture
def blockchain_factory():
    """
    BlockChainインスタンスを作成するファクトリfixture
    
    Returns:
        function: BlockChain作成関数
    """
    def _create_blockchain(enable_signature=True, with_keys=True):
        bc = BlockChain(enable_signature=enable_signature)
        if enable_signature and with_keys:
            bc.generate_key_pair()
        return bc
    
    return _create_blockchain


@pytest.fixture
def populated_blockchain():
    """
    複数のブロックが追加済みのBlockChainを作成するfixture
    
    Returns:
        BlockChain: 3つのブロックが追加されたBlockChain
    """
    bc = BlockChain(enable_signature=True)
    bc.generate_key_pair()
    
    # サンプルブロックを追加
    transactions = [
        (["Alice"], ["Bob"]),
        (["Bob"], ["Charlie"]), 
        (["Charlie"], ["Dave"])
    ]
    
    for input_data, output_data in transactions:
        bc.add_new_block(input_data, output_data)
    
    return bc


# pytestの設定
def pytest_configure(config):
    """pytest設定関数"""
    # カスタムマーカーを登録
    config.addinivalue_line(
        "markers", 
        "slow: テストの実行に時間がかかるテストをマーク"
    )
    config.addinivalue_line(
        "markers",
        "integration: 統合テストをマーク"
    )
    config.addinivalue_line(
        "markers",
        "crypto: 暗号化機能のテストをマーク"
    )


# テストレポートのカスタマイズ
def pytest_report_header(config):
    """テストレポートのヘッダーをカスタマイズ"""
    return [
        "署名機能テストスイート",
        "ブロックチェーン + デジタル署名の統合テスト"
    ]


# テスト失敗時の詳細情報
@pytest.fixture(autouse=True)
def test_info(request):
    """
    各テストの実行前後で情報を出力するauto-use fixture
    """
    test_name = request.node.name
    print(f"\n🚀 テスト開始: {test_name}")
    
    yield
    
    if hasattr(request.node, 'rep_call') and request.node.rep_call.failed:
        print(f"❌ テスト失敗: {test_name}")
    else:
        print(f"✅ テスト成功: {test_name}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """テスト結果をitem.repに保存するフック"""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)