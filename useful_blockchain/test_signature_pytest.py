"""
pytestを使用した署名機能のテストコード

SignatureManagerクラスとBlockChainクラスの署名機能を
pytestフレームワークを使用してテストします。
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
from cryptography.hazmat.primitives import serialization


class TestSignatureManager:
    """SignatureManagerクラスのテスト"""
    
    @pytest.fixture
    def signature_manager(self):
        """SignatureManagerのインスタンスを作成するfixture"""
        return SignatureManager()
    
    @pytest.fixture
    def signature_manager_with_keys(self):
        """鍵ペアが設定済みのSignatureManagerを作成するfixture"""
        sig_manager = SignatureManager()
        sig_manager.generate_key_pair()
        return sig_manager
    
    @pytest.fixture
    def test_data(self):
        """テスト用データのfixture"""
        return {"message": "Hello, Blockchain!", "value": 100}
    
    def test_key_pair_generation(self, signature_manager):
        """鍵ペア生成のテスト"""
        private_key, public_key = signature_manager.generate_key_pair()
        
        assert private_key is not None
        assert public_key is not None
        assert signature_manager.private_key is not None
        assert signature_manager.public_key is not None
    
    def test_key_pair_generation_different_sizes(self, signature_manager):
        """異なる鍵サイズでの鍵ペア生成テスト"""
        key_sizes = [1024, 2048, 4096]
        
        for size in key_sizes:
            private_key, public_key = signature_manager.generate_key_pair(size)
            assert private_key is not None
            assert public_key is not None
            assert private_key.key_size == size
    
    def test_sign_data_dict(self, signature_manager_with_keys, test_data):
        """辞書データの署名テスト"""
        signature = signature_manager_with_keys.sign_data(test_data)
        
        assert signature is not None
        assert isinstance(signature, bytes)
        assert len(signature) > 0
    
    def test_sign_data_string(self, signature_manager_with_keys):
        """文字列データの署名テスト"""
        test_string = "Test string for signing"
        signature = signature_manager_with_keys.sign_data(test_string)
        
        assert signature is not None
        assert isinstance(signature, bytes)
        assert len(signature) > 0
    
    def test_sign_data_without_keys(self, signature_manager):
        """鍵が設定されていない状態での署名テスト"""
        with pytest.raises(ValueError, match="秘密鍵が設定されていません"):
            signature_manager.sign_data("test data")
    
    def test_verify_signature_valid(self, signature_manager_with_keys, test_data):
        """正しい署名の検証テスト"""
        signature = signature_manager_with_keys.sign_data(test_data)
        is_valid = signature_manager_with_keys.verify_signature(test_data, signature)
        
        assert is_valid is True
    
    def test_verify_signature_invalid_data(self, signature_manager_with_keys, test_data):
        """異なるデータでの署名検証テスト（失敗ケース）"""
        signature = signature_manager_with_keys.sign_data(test_data)
        modified_data = {"message": "Modified message", "value": 200}
        is_valid = signature_manager_with_keys.verify_signature(modified_data, signature)
        
        assert is_valid is False
    
    def test_verify_signature_with_external_public_key(self, signature_manager_with_keys, test_data):
        """外部公開鍵を使った署名検証テスト"""
        signature = signature_manager_with_keys.sign_data(test_data)
        exported_key = signature_manager_with_keys.export_public_key()
        imported_key = signature_manager_with_keys.import_public_key(exported_key)
        
        is_valid = signature_manager_with_keys.verify_signature(test_data, signature, imported_key)
        
        assert is_valid is True
    
    def test_verify_signature_without_public_key(self, signature_manager):
        """公開鍵が設定されていない状態での検証テスト"""
        with pytest.raises(ValueError, match="公開鍵が設定されていません"):
            signature_manager.verify_signature("test", b"fake_signature")
    
    @pytest.mark.parametrize("export_format", ["pem", "der", "PEM", "DER"])
    def test_export_public_key_formats(self, signature_manager_with_keys, export_format):
        """公開鍵の異なる形式でのエクスポートテスト"""
        exported_key = signature_manager_with_keys.export_public_key(export_format)
        
        assert exported_key is not None
        assert isinstance(exported_key, bytes)
        assert len(exported_key) > 0
    
    def test_export_public_key_invalid_format(self, signature_manager_with_keys):
        """無効な形式での公開鍵エクスポートテスト"""
        with pytest.raises(ValueError, match="サポートされていない形式です"):
            signature_manager_with_keys.export_public_key("invalid")
    
    def test_export_public_key_without_key(self, signature_manager):
        """鍵が設定されていない状態での公開鍵エクスポートテスト"""
        with pytest.raises(ValueError, match="公開鍵が設定されていません"):
            signature_manager.export_public_key()
    
    def test_import_public_key(self, signature_manager_with_keys):
        """公開鍵のインポートテスト"""
        exported_key = signature_manager_with_keys.export_public_key()
        imported_key = signature_manager_with_keys.import_public_key(exported_key)
        
        assert imported_key is not None
        # 元の公開鍵と同じ内容であることを確認
        original_exported = signature_manager_with_keys.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        imported_exported = imported_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        assert original_exported == imported_exported
    
    def test_sign_block(self, signature_manager_with_keys):
        """ブロックデータの署名テスト"""
        block_data = {
            "block_index": 1,
            "timestamp": "2023-01-01 12:00:00",
            "data": {"from": "Alice", "to": "Bob", "amount": 100}
        }
        
        signed_block = signature_manager_with_keys.sign_block(block_data)
        
        assert "signature" in signed_block
        assert "public_key" in signed_block
        assert signed_block["block_index"] == 1  # 元のデータは保持されている
        assert isinstance(signed_block["signature"], str)  # 16進文字列
        assert isinstance(signed_block["public_key"], str)  # PEM文字列
    
    def test_verify_block_signature_valid(self, signature_manager_with_keys):
        """正しいブロック署名の検証テスト"""
        block_data = {
            "block_index": 1,
            "timestamp": "2023-01-01 12:00:00",
            "data": {"from": "Alice", "to": "Bob", "amount": 100}
        }
        
        signed_block = signature_manager_with_keys.sign_block(block_data)
        is_valid = signature_manager_with_keys.verify_block_signature(signed_block)
        
        assert is_valid is True
    
    def test_verify_block_signature_invalid(self, signature_manager_with_keys):
        """改ざんされたブロック署名の検証テスト"""
        block_data = {
            "block_index": 1,
            "timestamp": "2023-01-01 12:00:00",
            "data": {"from": "Alice", "to": "Bob", "amount": 100}
        }
        
        signed_block = signature_manager_with_keys.sign_block(block_data)
        
        # ブロックデータを改ざん
        signed_block["data"]["amount"] = 999
        
        is_valid = signature_manager_with_keys.verify_block_signature(signed_block)
        
        assert is_valid is False
    
    def test_verify_block_signature_missing_signature(self, signature_manager_with_keys):
        """署名のないブロックの検証テスト"""
        block_data = {
            "block_index": 1,
            "timestamp": "2023-01-01 12:00:00",
            "data": {"from": "Alice", "to": "Bob", "amount": 100}
        }
        
        is_valid = signature_manager_with_keys.verify_block_signature(block_data)
        
        assert is_valid is False


class TestBlockChainWithSignature:
    """署名機能を有効にしたBlockChainクラスのテスト"""
    
    @pytest.fixture
    def blockchain_with_signature(self):
        """署名機能有効なBlockChainのfixture"""
        bc = BlockChain(enable_signature=True)
        bc.generate_key_pair()
        return bc
    
    @pytest.fixture
    def blockchain_without_signature(self):
        """署名機能無効なBlockChainのfixture"""
        return BlockChain(enable_signature=False)
    
    def test_blockchain_initialization_with_signature(self):
        """署名機能有効でのBlockChain初期化テスト"""
        bc = BlockChain(enable_signature=True)
        
        assert bc.enable_signature is True
        assert bc.signature_manager is not None
        assert isinstance(bc.signature_manager, SignatureManager)
    
    def test_blockchain_initialization_without_signature(self):
        """署名機能無効でのBlockChain初期化テスト"""
        bc = BlockChain(enable_signature=False)
        
        assert bc.enable_signature is False
        assert bc.signature_manager is None
    
    def test_generate_key_pair_enabled(self, blockchain_with_signature):
        """署名機能有効時の鍵ペア生成テスト"""
        keys = blockchain_with_signature.generate_key_pair()
        
        assert keys is not None
        assert len(keys) == 2  # (private_key, public_key)
    
    def test_generate_key_pair_disabled(self, blockchain_without_signature):
        """署名機能無効時の鍵ペア生成テスト"""
        keys = blockchain_without_signature.generate_key_pair()
        
        assert keys is None
    
    def test_add_signed_block(self, blockchain_with_signature):
        """署名付きブロック追加テスト"""
        input_data = ["sender1", "sender2"]
        output_data = ["receiver1", "receiver2"]
        
        block = blockchain_with_signature.add_new_block(input_data, output_data)
        
        assert "signature" in block
        assert "public_key" in block
        assert block["block_index"] == 1
        assert len(blockchain_with_signature.chain) == 1
    
    def test_add_unsigned_block(self, blockchain_without_signature):
        """署名なしブロック追加テスト"""
        input_data = ["sender1"]
        output_data = ["receiver1"]
        
        block = blockchain_without_signature.add_new_block(input_data, output_data)
        
        assert "signature" not in block
        assert "public_key" not in block
        assert block["block_index"] == 1
        assert len(blockchain_without_signature.chain) == 1
    
    def test_verify_block_signature_valid(self, blockchain_with_signature):
        """正しいブロック署名の検証テスト"""
        blockchain_with_signature.add_new_block(["sender"], ["receiver"])
        
        is_valid = blockchain_with_signature.verify_block_signature(1)
        
        assert is_valid is True
    
    def test_verify_block_signature_invalid_index(self, blockchain_with_signature):
        """無効なインデックスでのブロック署名検証テスト"""
        blockchain_with_signature.add_new_block(["sender"], ["receiver"])
        
        # 無効なインデックス
        assert blockchain_with_signature.verify_block_signature(0) is False
        assert blockchain_with_signature.verify_block_signature(2) is False
        assert blockchain_with_signature.verify_block_signature(-1) is False
    
    def test_verify_block_signature_disabled(self, blockchain_without_signature):
        """署名機能無効時のブロック署名検証テスト"""
        blockchain_without_signature.add_new_block(["sender"], ["receiver"])
        
        is_valid = blockchain_without_signature.verify_block_signature(1)
        
        assert is_valid is False
    
    def test_verify_all_signatures(self, blockchain_with_signature):
        """全ブロック署名検証テスト"""
        # 複数ブロックを追加
        blockchain_with_signature.add_new_block(["sender1"], ["receiver1"])
        blockchain_with_signature.add_new_block(["sender2"], ["receiver2"])
        blockchain_with_signature.add_new_block(["sender3"], ["receiver3"])
        
        results = blockchain_with_signature.verify_all_signatures()
        
        assert len(results) == 3
        assert all(result is True for result in results.values())
        assert "block_1" in results
        assert "block_2" in results
        assert "block_3" in results
    
    def test_verify_all_signatures_disabled(self, blockchain_without_signature):
        """署名機能無効時の全ブロック署名検証テスト"""
        blockchain_without_signature.add_new_block(["sender"], ["receiver"])
        
        results = blockchain_without_signature.verify_all_signatures()
        
        assert results == {}
    
    def test_export_public_key_enabled(self, blockchain_with_signature):
        """署名機能有効時の公開鍵エクスポートテスト"""
        public_key = blockchain_with_signature.export_public_key()
        
        assert public_key is not None
        assert isinstance(public_key, bytes)
        assert b"BEGIN PUBLIC KEY" in public_key
    
    def test_export_public_key_disabled(self, blockchain_without_signature):
        """署名機能無効時の公開鍵エクスポートテスト"""
        public_key = blockchain_without_signature.export_public_key()
        
        assert public_key is None
    
    @pytest.mark.parametrize("num_blocks", [1, 5, 10])
    def test_multiple_blocks_signature_integrity(self, blockchain_with_signature, num_blocks):
        """複数ブロックでの署名整合性テスト"""
        # 指定数のブロックを追加
        for i in range(num_blocks):
            blockchain_with_signature.add_new_block([f"sender{i}"], [f"receiver{i}"])
        
        # すべてのブロックの署名を検証
        results = blockchain_with_signature.verify_all_signatures()
        
        assert len(results) == num_blocks
        assert all(result is True for result in results.values())
    
    def test_blockchain_chain_integrity(self, blockchain_with_signature):
        """ブロックチェーンのチェーン整合性テスト"""
        # 複数ブロックを追加
        block1 = blockchain_with_signature.add_new_block(["sender1"], ["receiver1"])
        block2 = blockchain_with_signature.add_new_block(["sender2"], ["receiver2"])
        block3 = blockchain_with_signature.add_new_block(["sender3"], ["receiver3"])
        
        # チェーンの整合性を確認
        assert len(blockchain_with_signature.chain) == 3
        assert blockchain_with_signature.chain[0] == block1
        assert blockchain_with_signature.chain[1] == block2
        assert blockchain_with_signature.chain[2] == block3
        
        # ハッシュチェーンの整合性を確認
        assert block2["block_header"]["prev_hash"] == block1["block_header"]["tran_hash"]
        assert block3["block_header"]["prev_hash"] == block2["block_header"]["tran_hash"]


class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    def test_signature_manager_import_invalid_key(self):
        """無効な公開鍵インポートのテスト"""
        sig_manager = SignatureManager()
        
        with pytest.raises(Exception):  # 具体的な例外はcryptographyライブラリに依存
            sig_manager.import_public_key(b"invalid key data")
    
    def test_blockchain_verify_nonexistent_block(self):
        """存在しないブロックの署名検証テスト"""
        bc = BlockChain(enable_signature=True)
        bc.generate_key_pair()
        
        # ブロックを追加せずに検証を試行
        is_valid = bc.verify_block_signature(1)
        
        assert is_valid is False


class TestIntegration:
    """統合テスト"""
    
    def test_full_workflow(self):
        """完全なワークフローのテスト"""
        # 1. 署名機能有効でブロックチェーン作成
        bc = BlockChain(enable_signature=True)
        
        # 2. 鍵ペア生成
        keys = bc.generate_key_pair()
        assert keys is not None
        
        # 3. 複数ブロック追加
        transactions = [
            (["Alice"], ["Bob"]),
            (["Bob"], ["Charlie"]),
            (["Charlie"], ["Dave"])
        ]
        
        for input_data, output_data in transactions:
            block = bc.add_new_block(input_data, output_data)
            assert "signature" in block
            assert "public_key" in block
        
        # 4. 全ブロック署名検証
        results = bc.verify_all_signatures()
        assert len(results) == 3
        assert all(result is True for result in results.values())
        
        # 5. 個別ブロック検証
        for i in range(1, 4):
            assert bc.verify_block_signature(i) is True
        
        # 6. 公開鍵エクスポート
        public_key = bc.export_public_key()
        assert public_key is not None
        
        print("✅ 完全なワークフローテストが成功しました")


if __name__ == "__main__":
    # pytestを直接実行する場合
    pytest.main([__file__, "-v"])