# easy_blockchain

you can use blockchain easily.
please use for prototype

簡単にブロックチェーンを使うためのライブラリ．
IoTに組み込んだりなど，簡易的なプロトタイプ作成に使ってください．

## useful_blockchain 概要

- 提供クラス: 
  - `useful_blockchain.blockchain.BlockChain`
  - `useful_blockchain.signature.SignatureManager`
- 目的: プロトタイプ・学習向けの極小ブロックチェーン実装。
- 主なメソッド:
  - `add_new_block(input_data, output_data)`: 新しいトランザクションを作成し，直前ブロックのハッシュと組み合わせて末尾にブロックを追加します（戻り値は追加されたブロックの辞書）。
  - `dump(block_index=0)`: チェーン全体または指定インデックスのブロックを簡易表示します。
  - `generate_key_pair()`: デジタル署名用の鍵ペアを生成します（署名機能有効時のみ）。
  - `verify_block_signature(block_index)`: 指定ブロックの署名を検証します。
- ブロック構造（辞書）:
  - `block_index`: 1始まりの連番
  - `block_item`: 生成日時（`YYYY-MM-DD HH:MM:SS`）
  - `block_header.prev_hash`: 直前ブロックのトランザクションハッシュ（先頭ブロックのみ乱数シードから生成）
  - `block_header.tran_hash`: `sha256(prev_hash + sha256(json(tran_body)))`
  - `tran_counter`: 入力と出力の要素数の合計
  - `tran_body.input_data` / `tran_body.output_data`: 追加時に渡した値
- ハッシュ化: `sha256` による簡易的な整合性保証（改ざん検知の学習・デモ用途）。

### 使い方（例）

#### 基本的な使い方

```python
from useful_blockchain.blockchain import BlockChain

bc = BlockChain()
bc.add_new_block(["a"], ["b"])
bc.add_new_block(["c"], ["d"])
print(bc.chain)  # チェーン配列（各ブロックは dict）
```

#### 署名機能付きブロックチェーン

```python
from useful_blockchain.blockchain import BlockChain

# 署名機能を有効にしてブロックチェーンを作成
bc = BlockChain(enable_signature=True)

# 鍵ペアを生成
private_key, public_key = bc.generate_key_pair()

# 署名付きブロックを追加
bc.add_new_block(["sender_a"], ["receiver_b"])
bc.add_new_block(["sender_c"], ["receiver_d"])

# 署名を検証
print(bc.verify_block_signature(1))  # True（署名が正しい場合）
print(bc.verify_all_signatures())    # 全ブロックの検証結果
```

#### デジタル署名単体での使用

```python
from useful_blockchain.signature import SignatureManager

sig_manager = SignatureManager()
private_key, public_key = sig_manager.generate_key_pair()

# データに署名
data = {"message": "Hello, Blockchain!"}
signature = sig_manager.sign_data(data)

# 署名を検証
is_valid = sig_manager.verify_signature(data, signature)
print(f"署名検証結果: {is_valid}")
```

## デジタル署名機能について

- RSA暗号化を使用したデジタル署名機能を提供
- 各ブロックに署名を付与し、データの完全性と認証を保証
- 署名の生成・検証・鍵管理機能を含む
- PEM形式での公開鍵エクスポート/インポートに対応

### 注意事項

- 合意形成（PoW/PoS等），P2P，難易度調整などは未実装です。
- デジタル署名機能は基本的な実装であり、実運用レベルの堅牢性は保証されません。
- 実運用向けではなく，教育・試作・デモ用途を想定しています。

# 今後やること

ブロックチェーンのデータ形式をjsonにするなど柔軟化する．

---

# English Documentation

## useful_blockchain Overview

- Provided Classes:
  - `useful_blockchain.blockchain.BlockChain`
  - `useful_blockchain.signature.SignatureManager`
- Purpose: Minimal blockchain implementation for prototyping and learning.
- Main Methods:
  - `add_new_block(input_data, output_data)`: Creates a new transaction and adds a block to the end of the chain by combining it with the hash of the previous block (returns the dictionary of the added block).
  - `dump(block_index=0)`: Simple display of the entire chain or a block at the specified index.
  - `generate_key_pair()`: Generates key pairs for digital signatures (only when signature feature is enabled).
  - `verify_block_signature(block_index)`: Verifies the signature of the specified block.
- Block Structure (dictionary):
  - `block_index`: Sequential number starting from 1
  - `block_item`: Generation timestamp (`YYYY-MM-DD HH:MM:SS`)
  - `block_header.prev_hash`: Transaction hash of the previous block (generated from random seed only for the first block)
  - `block_header.tran_hash`: `sha256(prev_hash + sha256(json(tran_body)))`
  - `tran_counter`: Total number of input and output elements
  - `tran_body.input_data` / `tran_body.output_data`: Values passed during addition
- Hashing: Simple integrity assurance by `sha256` (for learning and demonstration purposes of tampering detection).

### Usage Examples

#### Basic Usage

```python
from useful_blockchain.blockchain import BlockChain

bc = BlockChain()
bc.add_new_block(["a"], ["b"])
bc.add_new_block(["c"], ["d"])
print(bc.chain)  # Chain array (each block is a dict)
```

#### Blockchain with Signature Feature

```python
from useful_blockchain.blockchain import BlockChain

# Create blockchain with signature feature enabled
bc = BlockChain(enable_signature=True)

# Generate key pair
private_key, public_key = bc.generate_key_pair()

# Add signed blocks
bc.add_new_block(["sender_a"], ["receiver_b"])
bc.add_new_block(["sender_c"], ["receiver_d"])

# Verify signatures
print(bc.verify_block_signature(1))  # True (if signature is correct)
print(bc.verify_all_signatures())    # Verification results for all blocks
```

#### Standalone Digital Signature Usage

```python
from useful_blockchain.signature import SignatureManager

sig_manager = SignatureManager()
private_key, public_key = sig_manager.generate_key_pair()

# Sign data
data = {"message": "Hello, Blockchain!"}
signature = sig_manager.sign_data(data)

# Verify signature
is_valid = sig_manager.verify_signature(data, signature)
print(f"Signature verification result: {is_valid}")
```

## About Digital Signature Feature

- Provides digital signature functionality using RSA encryption
- Adds signatures to each block to ensure data integrity and authentication
- Includes signature generation, verification, and key management functions
- Supports public key export/import in PEM format

### Important Notes

- Consensus mechanisms (PoW/PoS, etc.), P2P, and difficulty adjustment are not implemented.
- The digital signature feature is a basic implementation and does not guarantee production-level robustness.
- Intended for educational, prototyping, and demonstration purposes, not for production use.

# commands for me

```
python3 setup.py bdist_wheel sdist
twine upload -r pypi dist/*
```
