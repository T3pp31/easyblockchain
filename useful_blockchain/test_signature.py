"""
署名機能のテストコード

SignatureManagerクラスとBlockChainクラスの署名機能をテストします。
"""

import sys
import os

# パッケージをインポートするためのパス設定
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from useful_blockchain.signature import SignatureManager
from useful_blockchain.blockchain import BlockChain


def test_signature_manager():
    """
    SignatureManagerクラスの基本機能をテスト
    """
    print("=== SignatureManager テスト開始 ===")
    
    # インスタンス作成
    sig_manager = SignatureManager()
    
    # 鍵ペア生成
    print("1. 鍵ペア生成テスト")
    private_key, public_key = sig_manager.generate_key_pair()
    assert private_key is not None, "秘密鍵が生成されませんでした"
    assert public_key is not None, "公開鍵が生成されませんでした"
    print("✓ 鍵ペア生成成功")
    
    # データ署名テスト
    print("2. データ署名テスト")
    test_data = {"message": "Hello, Blockchain!", "value": 100}
    signature = sig_manager.sign_data(test_data)
    assert signature is not None, "署名が生成されませんでした"
    print("✓ データ署名成功")
    
    # 署名検証テスト
    print("3. 署名検証テスト")
    is_valid = sig_manager.verify_signature(test_data, signature)
    assert is_valid == True, "正しい署名の検証に失敗しました"
    print("✓ 署名検証成功")
    
    # 無効な署名の検証テスト
    print("4. 無効署名検証テスト")
    invalid_data = {"message": "Modified data", "value": 200}
    is_invalid = sig_manager.verify_signature(invalid_data, signature)
    assert is_invalid == False, "無効な署名が正しいと判定されました"
    print("✓ 無効署名の検出成功")
    
    # 公開鍵エクスポート/インポートテスト
    print("5. 公開鍵エクスポート/インポートテスト")
    exported_key = sig_manager.export_public_key()
    imported_key = sig_manager.import_public_key(exported_key)
    assert imported_key is not None, "公開鍵のインポートに失敗しました"
    
    # インポートした公開鍵で検証
    is_valid_imported = sig_manager.verify_signature(test_data, signature, imported_key)
    assert is_valid_imported == True, "インポートした公開鍵での検証に失敗しました"
    print("✓ 公開鍵エクスポート/インポート成功")
    
    print("=== SignatureManager テスト完了 ===\n")


def test_blockchain_with_signature():
    """
    署名機能を有効にしたBlockChainクラスをテスト
    """
    print("=== BlockChain署名機能テスト開始 ===")
    
    # 署名機能を有効にしてブロックチェーンを作成
    print("1. 署名機能有効ブロックチェーン作成")
    bc = BlockChain(enable_signature=True)
    assert bc.enable_signature == True, "署名機能が有効になっていません"
    assert bc.signature_manager is not None, "SignatureManagerが初期化されていません"
    print("✓ 署名機能有効ブロックチェーン作成成功")
    
    # 鍵ペア生成
    print("2. 鍵ペア生成")
    keys = bc.generate_key_pair()
    assert keys is not None, "鍵ペア生成に失敗しました"
    print("✓ 鍵ペア生成成功")
    
    # 署名付きブロック追加
    print("3. 署名付きブロック追加")
    block1 = bc.add_new_block(["sender1"], ["receiver1"])
    assert 'signature' in block1, "ブロックに署名が含まれていません"
    assert 'public_key' in block1, "ブロックに公開鍵が含まれていません"
    print("✓ 署名付きブロック追加成功")
    
    # 複数ブロック追加
    print("4. 複数署名付きブロック追加")
    block2 = bc.add_new_block(["sender2"], ["receiver2"])
    block3 = bc.add_new_block(["sender3"], ["receiver3"])
    assert len(bc.chain) == 3, "ブロックが正しく追加されていません"
    print("✓ 複数署名付きブロック追加成功")
    
    # 個別ブロック署名検証
    print("5. 個別ブロック署名検証")
    result1 = bc.verify_block_signature(1)
    result2 = bc.verify_block_signature(2)
    result3 = bc.verify_block_signature(3)
    assert result1 == True, "ブロック1の署名検証に失敗しました"
    assert result2 == True, "ブロック2の署名検証に失敗しました"
    assert result3 == True, "ブロック3の署名検証に失敗しました"
    print("✓ 個別ブロック署名検証成功")
    
    # 全ブロック署名検証
    print("6. 全ブロック署名検証")
    all_results = bc.verify_all_signatures()
    assert all(result == True for result in all_results.values()), "一部のブロックの署名検証に失敗しました"
    print("✓ 全ブロック署名検証成功")
    
    # 公開鍵エクスポート
    print("7. 公開鍵エクスポート")
    public_key = bc.export_public_key()
    assert public_key is not None, "公開鍵のエクスポートに失敗しました"
    print("✓ 公開鍵エクスポート成功")
    
    print("=== BlockChain署名機能テスト完了 ===\n")


def test_blockchain_without_signature():
    """
    署名機能を無効にしたBlockChainクラスをテスト
    """
    print("=== BlockChain通常モードテスト開始 ===")
    
    # 通常のブロックチェーンを作成
    print("1. 通常ブロックチェーン作成")
    bc = BlockChain(enable_signature=False)
    assert bc.enable_signature == False, "署名機能が無効になっていません"
    assert bc.signature_manager is None, "SignatureManagerが無効になっていません"
    print("✓ 通常ブロックチェーン作成成功")
    
    # 通常ブロック追加
    print("2. 通常ブロック追加")
    block1 = bc.add_new_block(["sender1"], ["receiver1"])
    assert 'signature' not in block1, "署名が含まれてしまっています"
    assert 'public_key' not in block1, "公開鍵が含まれてしまっています"
    print("✓ 通常ブロック追加成功")
    
    # 署名機能の無効確認
    print("3. 署名機能無効確認")
    result = bc.generate_key_pair()
    assert result is None, "署名機能が無効なのに鍵ペアが生成されました"
    
    signature_result = bc.verify_block_signature(1)
    assert signature_result == False, "署名機能が無効なのに検証が実行されました"
    print("✓ 署名機能無効確認成功")
    
    print("=== BlockChain通常モードテスト完了 ===\n")


def test_edge_cases():
    """
    エッジケースのテスト
    """
    print("=== エッジケーステスト開始 ===")
    
    # 署名マネージャー鍵なしテスト
    print("1. 鍵未設定での署名テスト")
    sig_manager = SignatureManager()
    try:
        sig_manager.sign_data("test")
        assert False, "鍵未設定で署名が成功してしまいました"
    except ValueError:
        print("✓ 鍵未設定での署名エラー正常")
    
    # 無効なブロックインデックステスト
    print("2. 無効ブロックインデックステスト")
    bc = BlockChain(enable_signature=True)
    bc.generate_key_pair()
    bc.add_new_block(["test"], ["test"])
    
    invalid_result = bc.verify_block_signature(0)  # 無効なインデックス
    assert invalid_result == False, "無効なインデックスで検証が成功してしまいました"
    
    invalid_result2 = bc.verify_block_signature(10)  # 存在しないブロック
    assert invalid_result2 == False, "存在しないブロックで検証が成功してしまいました"
    print("✓ 無効ブロックインデックステスト成功")
    
    print("=== エッジケーステスト完了 ===\n")


def main():
    """
    すべてのテストを実行
    """
    print("署名機能テストスイート開始\n")
    
    try:
        # 基本的な署名機能テスト
        test_signature_manager()
        
        # ブロックチェーン署名機能テスト
        test_blockchain_with_signature()
        
        # ブロックチェーン通常モードテスト
        test_blockchain_without_signature()
        
        # エッジケーステスト
        test_edge_cases()
        
        print("🎉 すべてのテストが成功しました！")
        
    except Exception as e:
        print(f"❌ テストに失敗しました: {e}")
        return False
    
    return True


if __name__ == "__main__":
    main()