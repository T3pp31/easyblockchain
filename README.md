# easy_blockchain

you can use blockchain easily.
please use for prototype

簡単にブロックチェーンを使うためのライブラリ．
IoTに組み込んだりなど，簡易的なプロトタイプ作成に使ってください．

## useful_blockchain 概要

- 提供クラス: `useful_blockchain.blockchain.BlockChain`
- 目的: プロトタイプ・学習向けの極小ブロックチェーン実装。
- 主なメソッド:
  - `add_new_block(input_data, output_data)`: 新しいトランザクションを作成し，直前ブロックのハッシュと組み合わせて末尾にブロックを追加します（戻り値は追加されたブロックの辞書）。
  - `dump(block_index=0)`: チェーン全体または指定インデックスのブロックを簡易表示します。
- ブロック構造（辞書）:
  - `block_index`: 1始まりの連番
  - `block_item`: 生成日時（`YYYY-MM-DD HH:MM:SS`）
  - `block_header.prev_hash`: 直前ブロックのトランザクションハッシュ（先頭ブロックのみ乱数シードから生成）
  - `block_header.tran_hash`: `sha256(prev_hash + sha256(json(tran_body)))`
  - `tran_counter`: 入力と出力の要素数の合計
  - `tran_body.input_data` / `tran_body.output_data`: 追加時に渡した値
- ハッシュ化: `sha256` による簡易的な整合性保証（改ざん検知の学習・デモ用途）。

### 使い方（例）

```
from useful_blockchain.blockchain import BlockChain

bc = BlockChain()
bc.add_new_block(["a"], ["b"])
bc.add_new_block(["c"], ["d"])
print(bc.chain)  # チェーン配列（各ブロックは dict）
```

### 注意事項

- 合意形成（PoW/PoS等），P2P，署名検証，難易度調整などは未実装です。
- 実運用向けではなく，教育・試作・デモ用途を想定しています。

# 今後やること

ブロックチェーンのデータ形式をjsonにするなど柔軟化する．

# commands for me

```
python3 setup.py bdist_wheel sdist
twine upload -r pypi dist/*
```
