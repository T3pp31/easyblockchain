"""
シンプルなブロックチェーンの実装

このモジュールは基本的なブロックチェーンの機能を提供します。
各ブロックは前のブロックのハッシュ値を含んでおり、チェーン状に連結されています。
"""

import datetime as dt
import hashlib
import json
import os
from .signature import SignatureManager


class BlockChain(object):
    """
    ブロックチェーンクラス
    
    ブロックを連結してチェーン状に管理するクラスです。
    各ブロックには取引データ、タイムスタンプ、前のブロックへの参照が含まれます。
    """
    
    def __init__(self, enable_signature=False):
        """
        ブロックチェーンを初期化
        
        空のチェーンリストを作成します。
        
        Args:
            enable_signature (bool): 署名機能を有効にするかどうか
        """
        self.chain = []  # ブロックチェーンの本体（ブロックのリスト）
        self.enable_signature = enable_signature
        self.signature_manager = SignatureManager() if enable_signature else None

    def __generate_random_hash(self):
        """
        最初のブロック用のランダムハッシュを生成
        
        ジェネシス（最初の）ブロックには前のブロックが存在しないため、
        ランダムなハッシュ値を生成して使用します。
        
        Returns:
            str: 64文字のSHA256ハッシュ値
        """
        # 16バイトのランダムデータを生成
        random_data = os.urandom(16)
        # SHA256でハッシュ化
        hash_object = hashlib.sha256(random_data)
        random_hash = hash_object.hexdigest()
        return random_hash

    def add_new_block(self, input_data, output_data):
        """
        新しいブロックをチェーンに追加
        
        入力データと出力データから新しい取引を作成し、
        それを含むブロックをチェーンに追加します。
        
        Args:
            input_data: 取引の入力データ
            output_data: 取引の出力データ
            
        Returns:
            dict: 作成された新しいブロック
        """
        # 新しい取引を作成
        new_transaction = self.__create_new_transaction(input_data, output_data)

        # 前のブロックのハッシュ値を取得
        if len(self.chain) > 0:
            # チェーンに既存のブロックがある場合、最後のブロックのハッシュを使用
            prev_hash = self.chain[-1]["block_header"]["tran_hash"]
        else:
            # 最初のブロック（ジェネシスブロック）の場合、ランダムハッシュを生成
            prev_hash = self.__generate_random_hash()

        # 新しいブロックを作成
        new_block = {
            "block_index": len(self.chain) + 1,  # ブロック番号（1から開始）
            "block_item": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # タイムスタンプ
            "block_header": {
                "prev_hash": prev_hash,  # 前のブロックのハッシュ値
                "tran_hash": self.__hash(
                    prev_hash + self.__calc_tran_hash(new_transaction)
                ),  # 現在のブロックのハッシュ値（前のハッシュ + 取引ハッシュ）
            },
            "tran_counter": len(input_data) + len(output_data),  # 取引データの総数
            "tran_body": new_transaction,  # 取引の内容
        }
        
        # 署名機能が有効な場合、ブロックに署名を追加
        if self.enable_signature and self.signature_manager:
            new_block = self.signature_manager.sign_block(new_block)
        
        # チェーンにブロックを追加
        self.chain.append(new_block)
        return new_block

    def __create_new_transaction(self, input_data, output_data):
        """
        新しい取引を作成
        
        プライベートメソッド：入力データと出力データから取引オブジェクトを作成します。
        
        Args:
            input_data: 取引の入力データ
            output_data: 取引の出力データ
            
        Returns:
            dict: 取引オブジェクト
        """
        new_transaction = {
            "input_data": input_data,   # 取引の入力（送信者情報など）
            "output_data": output_data, # 取引の出力（受信者情報など）
        }
        return new_transaction

    def __calc_tran_hash(self, new_transaction):
        """
        取引のハッシュ値を計算
        
        プライベートメソッド：取引データをJSON文字列に変換してハッシュ化します。
        
        Args:
            new_transaction (dict): 取引オブジェクト
            
        Returns:
            str: 取引のSHA256ハッシュ値
        """
        # 取引をJSON文字列に変換（キーをソートして一意性を保証）
        tran_string = json.dumps(new_transaction, sort_keys=True).encode()
        return self.__hash(tran_string)

    def __hash(self, str_seed):
        """
        文字列のSHA256ハッシュ値を計算
        
        プライベートメソッド：任意の文字列データをSHA256でハッシュ化します。
        
        Args:
            str_seed: ハッシュ化する元データ
            
        Returns:
            str: SHA256ハッシュ値（64文字の16進数文字列）
        """
        return hashlib.sha256(str(str_seed).encode()).hexdigest()

    def dump(self, block_index=0):
        """
        ブロックチェーンの内容を表示
        
        ブロックチェーン全体または指定したブロックの内容を
        JSON形式で整形して出力します。
        
        Args:
            block_index (int): 表示するブロックのインデックス（0=全体）
        """
        if block_index == 0:
            # 全体のチェーンを表示
            print(json.dumps(self.chain, sort_key=False, indent=2))
        else:
            # 指定されたブロックのみを表示
            print(json.dumps(self.chain(block_index, sort_key=False, indent=2)))
    
    def generate_key_pair(self):
        """
        新しい鍵ペアを生成
        
        署名機能が有効な場合のみ利用可能です。
        
        Returns:
            tuple: (private_key, public_key) または None（署名機能が無効な場合）
        """
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return None
        
        return self.signature_manager.generate_key_pair()
    
    def verify_block_signature(self, block_index):
        """
        指定したブロックの署名を検証
        
        Args:
            block_index (int): 検証するブロックのインデックス（1から開始）
            
        Returns:
            bool: 署名が正しい場合True、そうでなければFalse
        """
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return False
        
        if block_index < 1 or block_index > len(self.chain):
            print("無効なブロックインデックスです。")
            return False
        
        block = self.chain[block_index - 1]  # インデックスは0から開始
        
        if 'signature' not in block:
            print("このブロックには署名がありません。")
            return False
        
        return self.signature_manager.verify_block_signature(block)
    
    def verify_all_signatures(self):
        """
        チェーン内のすべてのブロックの署名を検証
        
        Returns:
            dict: 各ブロックの検証結果
        """
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return {}
        
        results = {}
        for i, block in enumerate(self.chain, 1):
            if 'signature' in block:
                results[f"block_{i}"] = self.signature_manager.verify_block_signature(block)
            else:
                results[f"block_{i}"] = None  # 署名なし
        
        return results
    
    def export_public_key(self):
        """
        公開鍵をエクスポート
        
        Returns:
            bytes: 公開鍵データ（PEM形式） または None
        """
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return None
        
        return self.signature_manager.export_public_key()


if __name__ == "__main__":
    bc = BlockChain()
    bc.add_new_block("test", "test1")
    bc.add_new_block("test3", "test4")
    print(bc.chain)
