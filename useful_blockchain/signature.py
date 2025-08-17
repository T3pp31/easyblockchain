"""
デジタル署名機能の実装

このモジュールはブロックチェーンで使用するデジタル署名機能を提供します。
RSA暗号化を使用して署名の生成と検証を行います。
"""

import hashlib
import json
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


class SignatureManager:
    """
    デジタル署名管理クラス
    
    RSA暗号を使用して鍵の生成、署名の作成、署名の検証を行います。
    """
    
    def __init__(self):
        """
        署名マネージャーを初期化
        """
        self.private_key = None
        self.public_key = None
    
    def generate_key_pair(self, key_size=2048):
        """
        RSA鍵ペアを生成
        
        Args:
            key_size (int): 鍵のサイズ（ビット）。デフォルトは2048ビット
            
        Returns:
            tuple: (private_key, public_key)
        """
        # 秘密鍵を生成
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size
        )
        
        # 公開鍵を取得
        self.public_key = self.private_key.public_key()
        
        return self.private_key, self.public_key
    
    def sign_data(self, data):
        """
        データに署名を付与
        
        Args:
            data: 署名対象のデータ（辞書、文字列、バイト）
            
        Returns:
            bytes: 署名データ
            
        Raises:
            ValueError: 秘密鍵が設定されていない場合
        """
        if self.private_key is None:
            raise ValueError("秘密鍵が設定されていません。generate_key_pair()を先に実行してください。")
        
        # データを文字列に変換
        if isinstance(data, dict):
            data_string = json.dumps(data, sort_keys=True)
        elif isinstance(data, str):
            data_string = data
        else:
            data_string = str(data)
        
        # データをバイト列に変換
        data_bytes = data_string.encode('utf-8')
        
        # 署名を生成
        signature = self.private_key.sign(
            data_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature
    
    def verify_signature(self, data, signature, public_key=None):
        """
        署名を検証
        
        Args:
            data: 署名対象のデータ
            signature (bytes): 検証する署名
            public_key: 公開鍵（指定しない場合は自身の公開鍵を使用）
            
        Returns:
            bool: 署名が正しい場合True、そうでなければFalse
        """
        # 公開鍵の設定
        if public_key is None:
            if self.public_key is None:
                raise ValueError("公開鍵が設定されていません。")
            verify_key = self.public_key
        else:
            verify_key = public_key
        
        # データを文字列に変換
        if isinstance(data, dict):
            data_string = json.dumps(data, sort_keys=True)
        elif isinstance(data, str):
            data_string = data
        else:
            data_string = str(data)
        
        # データをバイト列に変換
        data_bytes = data_string.encode('utf-8')
        
        try:
            # 署名を検証
            verify_key.verify(
                signature,
                data_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            return False
    
    def export_public_key(self, format='pem'):
        """
        公開鍵をエクスポート
        
        Args:
            format (str): エクスポート形式（'pem' または 'der'）
            
        Returns:
            bytes: エクスポートされた公開鍵
        """
        if self.public_key is None:
            raise ValueError("公開鍵が設定されていません。")
        
        if format.lower() == 'pem':
            return self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        elif format.lower() == 'der':
            return self.public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        else:
            raise ValueError("サポートされていない形式です。'pem'または'der'を指定してください。")
    
    def import_public_key(self, key_data):
        """
        公開鍵をインポート
        
        Args:
            key_data (bytes): インポートする公開鍵データ
            
        Returns:
            public_key: インポートされた公開鍵オブジェクト
        """
        return serialization.load_pem_public_key(key_data)
    
    def sign_block(self, block_data):
        """
        ブロックデータに署名を付与
        
        Args:
            block_data (dict): ブロックデータ
            
        Returns:
            dict: 署名付きブロックデータ
        """
        # ブロックデータをコピー（元データを変更しないため）
        signed_block = block_data.copy()
        
        # 署名を生成
        signature = self.sign_data(block_data)
        
        # 署名をブロックに追加
        signed_block['signature'] = signature.hex()  # バイナリデータを16進文字列に変換
        signed_block['public_key'] = self.export_public_key().decode('utf-8')
        
        return signed_block
    
    def verify_block_signature(self, signed_block):
        """
        署名付きブロックの署名を検証
        
        Args:
            signed_block (dict): 署名付きブロックデータ
            
        Returns:
            bool: 署名が正しい場合True、そうでなければFalse
        """
        if 'signature' not in signed_block or 'public_key' not in signed_block:
            return False
        
        # 署名と公開鍵を取得
        signature_hex = signed_block['signature']
        public_key_pem = signed_block['public_key'].encode('utf-8')
        
        # 署名をバイナリに変換
        signature = bytes.fromhex(signature_hex)
        
        # 公開鍵をインポート
        public_key = self.import_public_key(public_key_pem)
        
        # 署名を除いたブロックデータを作成
        block_data = signed_block.copy()
        del block_data['signature']
        del block_data['public_key']
        
        # 署名を検証
        return self.verify_signature(block_data, signature, public_key)


if __name__ == "__main__":
    # 使用例
    sig_manager = SignatureManager()
    
    # 鍵ペアを生成
    private_key, public_key = sig_manager.generate_key_pair()
    print("鍵ペアを生成しました")
    
    # テストデータ
    test_data = {"message": "Hello, Blockchain!", "timestamp": "2023-01-01"}
    
    # 署名を生成
    signature = sig_manager.sign_data(test_data)
    print(f"署名を生成しました: {signature.hex()[:50]}...")
    
    # 署名を検証
    is_valid = sig_manager.verify_signature(test_data, signature)
    print(f"署名検証結果: {is_valid}")