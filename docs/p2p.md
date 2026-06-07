# P2P ネットワーク

easyblockchain v2.0 の P2P ネットワーク層の解説です。分散ノード間でブロックチェーンを共有・同期するための仕組みを説明します。

## 概要

P2P 層は **asyncio + WebSocket + JSON** で実装されています。libp2p や gossip プロトコルは使わず、教育・試作向けにシンプルな設計としています。

| 項目 | 内容 |
|------|------|
| トランスポート | WebSocket（`websockets` ライブラリ） |
| シリアライズ | JSON（既存ブロック形式と整合） |
| エントリポイント | `useful_blockchain.network.node.Node` |
| 起動例 | `examples/run_node.py` |

v1 互換モードの `BlockChain()` 単体利用では P2P は動作しません。分散モードでは `Node` 経由でブロックを追加・同期してください。

## アーキテクチャ

```mermaid
flowchart TB
    subgraph app [Application]
        CLI[examples/run_node.py]
        Node[Node]
    end
    subgraph network [useful_blockchain/network]
        P2PServer[P2PServer]
        PeerConn[PeerConnection]
        Discovery[PeerDiscovery]
        Messages[messages.py]
    end
    subgraph core [Core]
        BC[BlockChain]
        Consensus[PoW / PoS]
    end
    CLI --> Node
    Node --> P2PServer
    Node --> Discovery
    Node --> BC
    Node --> Consensus
    P2PServer --> PeerConn
    PeerConn --> Messages
```

### コンポーネント

| ファイル | クラス | 役割 |
|---------|--------|------|
| `network/node.py` | `Node` | P2P・合意・チェーンを束ねるオーケストレータ |
| `network/server.py` | `P2PServer` | WebSocket サーバー起動、接続管理、`broadcast` |
| `network/peer.py` | `PeerConnection` | 1 ピアとの送受信ループ |
| `network/discovery.py` | `PeerDiscovery` | ブートストラップ + 任意 mDNS |
| `network/messages.py` | `MessageType` | 7 種のメッセージ定義と JSON シリアライズ |
| `network/tls.py` | — | WSS 用 `SSLContext` 構築 |
| `network/peer_auth.py` | — | 署名付き HELLO の生成・検証 |
| `network/rate_limit.py` | `SlidingWindowRateLimiter` | IP / ピア単位のレート制限 |
| `network/reconnect.py` | `ReconnectManager` | 指数バックオフ再接続 |

### Node のライフサイクル

**`start()` の処理順序:**

1. `P2PServer.start()` — WebSocket サーバーを起動
2. `PeerDiscovery.start_mdns()` — mDNS が有効なら LAN 内ピアをブラウズし、自ノードを advertise
3. `bootstrap_peers` の各 URL に `connect_peer()` で接続
4. PING ループを開始（`ping_interval_seconds` 間隔）
5. 接続済みピアへ HELLO をブロードキャスト

**`stop()` の処理順序:**

1. PING ループをキャンセル
2. mDNS を停止
3. 全ピア接続を閉じ、サーバーを停止

**インバウンド接続（`_handle_connection`）の処理:**

1. `asyncio.Lock` で同時接続数を排他制御
2. `len(peers) >= max_peers` の場合、WebSocket を `1013` で即クローズして拒否
3. 上限内なら `PeerConnection` を登録し `listen()` を開始

**`connect_peer(url)` の処理:**

1. 空 URL・自ノード URL・既接続 URL はスキップ
2. `P2PServer.connect_peer()` で WebSocket 接続（`max_peers` 超過時は失敗）
3. 成功時に HELLO を送信
4. 既知ピアリストを PEERS メッセージで送信

## プロトコル仕様

### メッセージ形式

すべてのメッセージは次の JSON 形式で WebSocket 上に送られます。

```json
{"type": "HELLO", "node_id": "...", "consensus_type": "pow", ...}
```

`type` フィールドは `MessageType` 列挙値の文字列です。エンコード・デコードは `encode_message()` / `decode_message()` が担当します。

### メッセージサイズとデコードエラー

| 項目 | 挙動 |
|------|------|
| サイズ上限 | `network.max_message_bytes`（デフォルト 1 MiB）。WebSocket 層の `max_size` と送信前チェックの両方に適用 |
| 超過ペイロード | WebSocket 層で拒否（`PayloadTooBig`）。接続は切断 |
| 不正 JSON / 未知 type | warning ログを出してスキップ。連続エラーが `rate_limit.max_decode_errors_before_disconnect` を超えると切断 |
| HELLO 前のメッセージ | `peer_auth.enabled` 時は HELLO 以外を拒否して切断 |

### メッセージ一覧

| Type | 用途 | 送信側が付与する主な payload |
|------|------|------------------------------|
| `HELLO` | ハンドシェイク | `node_id`, `consensus_type`, `chain_height`, `genesis_hash`, `public_key`, `signature`, `timestamp` |
| `PEERS` | ピアリスト交換 | `peers`（WebSocket URL のリスト） |
| `GET_CHAIN` | チェーン要求 | `from_height`, `limit`, `requester` |
| `CHAIN_RESPONSE` | チェーン応答 | `blocks`, `from_height`, `next_height`, `has_more`, `node_id` |
| `NEW_BLOCK` | 新ブロック通知 | `block`, `node_id` |
| `PING` | 死活監視 | `node_id` |
| `PONG` | PING 応答 | `node_id` |

### JSON 例

**HELLO（送信）**

```json
{
  "type": "HELLO",
  "node_id": "a1b2c3d4-...",
  "consensus_type": "pow",
  "chain_height": 3,
  "genesis_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...",
  "signature": "a1b2...",
  "timestamp": 1710000000
}
```

**PEERS**

```json
{
  "type": "PEERS",
  "peers": ["ws://127.0.0.1:8765", "ws://127.0.0.1:8766"]
}
```

**GET_CHAIN**

```json
{
  "type": "GET_CHAIN",
  "from_height": 1,
  "limit": 100,
  "requester": "a1b2c3d4-..."
}
```

`limit` を省略した場合、応答側は `network.chain_sync_batch_size` を使用します。

**CHAIN_RESPONSE**

```json
{
  "type": "CHAIN_RESPONSE",
  "blocks": [/* Block オブジェクトの配列 */],
  "from_height": 1,
  "next_height": 101,
  "has_more": true,
  "node_id": "a1b2c3d4-..."
}
```

`has_more` が `true` のとき、要求側は `next_height` から次のバッチを要求します。

**NEW_BLOCK**

```json
{
  "type": "NEW_BLOCK",
  "block": {/* Block オブジェクト */},
  "node_id": "a1b2c3d4-..."
}
```

### 通信フロー

```mermaid
sequenceDiagram
    participant N1 as Node1
    participant N2 as Node2
    N1->>N2: HELLO
    N1->>N2: PEERS
    N2->>N1: HELLO
    N2->>N1: PEERS
    Note over N1,N2: チェーン高さが低い方が GET_CHAIN を送信
    N1->>N2: GET_CHAIN
    N2->>N1: CHAIN_RESPONSE
    N1->>N2: NEW_BLOCK
    loop ping_interval_seconds ごと
        N1->>N2: PING
        N2->>N1: PONG
    end
```

### HELLO ハンドシェイクの検証

受信側 `Node._on_hello()` の挙動:

| 項目 | 検証 | 不一致時の動作 |
|------|------|----------------|
| `signature` / `timestamp` | `peer_auth.enabled` 時 | 署名またはタイムスタンプが不正なら切断 |
| `consensus_type` | あり | warning ログを出し、ピア接続を切断 |
| `chain_height` | 比較のみ | 相手の方が高ければ `GET_CHAIN` で同期 |
| `genesis_hash` | あり | warning ログを出し、ピア接続を切断 |

P2P 用 identity 鍵は `persistence.p2p_identity_file`（デフォルト `keys/p2p_identity.pem`）に保存されます。PoS のブロック署名鍵（`node.pem`）とは別です。

`genesis_hash` はチェーンが空なら `config/default.yaml` の `genesis.prev_hash`、それ以外は先頭ブロックの `block_header.prev_hash`（なければ設定値）です。同一ネットワーク内の全ノードは同じ `genesis.prev_hash` を設定してください。

## ピア発見

ノードは次の 3 経路でピアを発見します。

### 1. ブートストラップ

`config/default.yaml` の `bootstrap_peers` または CLI の `--bootstrap` で初期接続先を指定します。

```bash
uv run python examples/run_node.py --port 8766 --bootstrap ws://127.0.0.1:8765
```

### 2. PEERS 交換

接続確立後、各ノードは既知のピア URL リストを PEERS メッセージで共有します。受信側はリスト内のピアへ順次接続を試みます（`max_peers` まで）。

### 3. mDNS（任意）

LAN 内の他ノードを自動発見するオプション機能です。

**有効化手順:**

1. 依存をインストール: `uv pip install "useful_blockchain[mdns]"`（`zeroconf>=0.131`）
2. 設定で `mdns_enabled: true` にする

**注意:**

- mDNS は**ブラウズ + advertise**（LAN 内の相互発見）。`mdns_advertise_enabled: false` でブラウズのみにできます
- advertise 時の LAN IP は `mdns_advertise_host` で指定するか、空の場合は自動検出します
- 発見したピアの URL は `ws://{ipv4}:{port}` 形式（TLS 有効時は `wss://`）
- TXT レコードに `node_id`, `consensus_type`, `genesis_hash` を載せます
- `zeroconf` 未インストール時は warning ログを出し、P2P はブートストラップのみで続行します

## チェーン同期とフォーク解決

### 同期トリガー

- HELLO 受信時、相手の `chain_height` が自分より大きい
- `NEW_BLOCK` 受信時、ブロック追加に失敗した（`add_block` が `False` を返した）
- `Node.sync_chain()` を明示的に呼び出した

### GET_CHAIN / CHAIN_RESPONSE

1. 要求側は `GET_CHAIN` を送信（`from_height` は常に `1`）
2. 応答側は `blockchain.get_blocks_from(from_height)` でブロック列を返す
3. 要求側は 10 秒以内に `CHAIN_RESPONSE` を待つ（タイムアウト時は warning ログ）
4. 受信したチェーンで `consensus.select_canonical_chain()` により正規チェーンを選択
5. ローカルと異なる場合は `blockchain.replace_chain()` で置き換え

`get_blocks_from(1)` はチェーン全体を返します。`from_height < 1` の場合も全ブロックを返します。

### 新ブロックの伝播

`Node.add_block()` はローカルでブロックを生成したあと、トランスポートに応じて伝播します。

| `network.transport` | 伝播方式 |
|---------------------|----------|
| `websocket`（デフォルト） | 直接接続ピアへ `NEW_BLOCK` broadcast |
| `libp2p` | GossipSub トピック `/easyblockchain/blocks/1.0.0` へ publish |

受信側は `blockchain.add_block()` で検証・追加します。libp2p モードでは HELLO / チェーン同期はストリームプロトコル `/easyblockchain/chain-sync/1.0.0` を使います。

### libp2p トランスポート（オプション）

1. 依存をインストール: `uv pip install "useful_blockchain[libp2p]"`（Python 3.10+、macOS/Linux では `gmp` が必要な場合あり）
2. 設定で `network.transport: libp2p` にする
3. ブートストラップは `network.libp2p.bootstrap_peers` に multiaddr 形式（例: `/ip4/127.0.0.1/tcp/9000/p2p/12D3Koo...`）を指定

libp2p モードでは `Node.transport.local_url` が multiaddr を返します。

## 設定リファレンス

`config/default.yaml`、または環境変数 `EASYBLOCKCHAIN_CONFIG` で指定した YAML ファイルから読み込みます。

### `genesis` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `prev_hash` | 64 文字の `"0"` | 先頭ブロックの `prev_hash` および HELLO の `genesis_hash` 識別子 |

### `network` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `transport` | `"websocket"` | トランスポート種別（`websocket` / `libp2p`） |
| `host` | `"0.0.0.0"` | WebSocket サーバーのバインドアドレス |
| `port` | `8765` | リッスンポート（`0` で OS が空きポートを割当） |
| `bootstrap_peers` | `[]` | 起動時に接続するピア URL のリスト |
| `mdns_enabled` | `false` | mDNS ピア発見の有効化 |
| `mdns_service_name` | `"_easyblockchain._tcp.local."` | mDNS サービスタイプ |
| `mdns_advertise_enabled` | `true` | 自ノードの mDNS サービス登録 |
| `mdns_advertise_host` | `""` | advertise 用 IPv4（空なら自動検出） |
| `mdns_instance_name` | `""` | サービスインスタンス名（空なら `node_id` から生成） |
| `max_peers` | `25` | 同時接続ピア数の上限（インバウンド・アウトバウンド共通） |
| `max_message_bytes` | `1048576` | 1 メッセージあたりの最大バイト数（1 MiB） |
| `chain_sync_batch_size` | `100` | チェーン同期の1バッチあたり最大ブロック数 |
| `ping_interval_seconds` | `30` | PING 送信間隔（秒） |
| `connection_timeout_seconds` | `10` | 発信 WebSocket 接続のタイムアウト（秒） |
| `chain_sync_timeout_seconds` | `10` | チェーン同期完了待ちタイムアウト（秒） |
| `shutdown_peer_close_timeout_seconds` | `2` | 停止時のピア切断待ちタイムアウト（秒） |
| `shutdown_server_wait_timeout_seconds` | `3` | 停止時のサーバー終了待ちタイムアウト（秒） |
| `pong_timeout_seconds` | `90` | PING 送信後に PONG がない場合の切断までの秒数 |

#### `network.libp2p` セクション（`transport: libp2p` 時）

| キー | デフォルト | 説明 |
|------|-----------|------|
| `listen_port` | `0` | libp2p TCP リッスンポート（`0` で OS 割当） |
| `bootstrap_peers` | `[]` | ブートストラップ multiaddr のリスト |
| `gossipsub_mesh_n` | `6` | GossipSub メッシュの目標ピア数 |
| `gossipsub_heartbeat_interval` | `5.0` | GossipSub ハートビート間隔（秒） |

#### `network.tls` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `enabled` | `false` | WSS を有効化（`true` で `wss://`） |
| `cert_file` | `""` | サーバー証明書 PEM パス |
| `key_file` | `""` | サーバー秘密鍵 PEM パス |
| `ca_file` | `""` | クライアント検証用 CA（任意） |
| `verify_peer` | `false` | クライアント側でサーバー証明書を検証 |

開発用証明書は `scripts/generate_dev_certs.sh` で生成できます。

#### `network.peer_auth` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `enabled` | `true` | 署名付き HELLO によるピア認証 |
| `max_skew_seconds` | `300` | HELLO `timestamp` の許容ずれ（秒） |

#### `network.rate_limit` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `max_connections_per_ip_per_minute` | `10` | IP あたりの接続試行上限（1分） |
| `max_messages_per_peer_per_second` | `50` | ピアあたりの受信メッセージ上限（1秒） |
| `max_decode_errors_before_disconnect` | `5` | 連続デコードエラーで切断する閾値 |

#### `network.reconnect` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `enabled` | `true` | 切断後の自動再接続 |
| `initial_delay_seconds` | `1` | 初回リトライ待ち（秒） |
| `max_delay_seconds` | `60` | バックオフ上限（秒） |
| `max_attempts` | `0` | 最大試行回数（`0` は無制限） |
| `backoff_multiplier` | `2.0` | バックオフ倍率 |

`host` が `0.0.0.0` または空のとき、`local_url` は `ws://127.0.0.1:{port}`（または TLS 有効時 `wss://`）として報告されます。

### `node` セクション

| キー | デフォルト | 説明 |
|------|-----------|------|
| `data_dir` | `"./data"` | ノードデータの保存ディレクトリ |
| `node_id` | `""` | ノード ID（空の場合は自動生成） |
| `log_level` | `"INFO"` | ログレベル（`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`） |

## 利用手順

### CLI でノード起動

```bash
# ノード 1（PoW）
uv run python examples/run_node.py --consensus pow --port 8765

# ノード 2（ノード 1 に接続）
uv run python examples/run_node.py --consensus pow --port 8766 --bootstrap ws://127.0.0.1:8765

# デバッグログを有効化
uv run python examples/run_node.py --log-level DEBUG
```

### Python API

```python
import asyncio
from useful_blockchain.network.node import Node

async def main() -> None:
    node = Node(overrides={
        "consensus": {"type": "pow", "pow": {"initial_difficulty": 2}},
        "network": {"port": 8765, "bootstrap_peers": []},
    })
    await node.start()
    print(f"Listening on {node.p2p.local_url}")
    await node.add_block(["alice"], ["bob"])
    await node.stop()

asyncio.run(main())
```

### マルチノード検証スクリプト

3 ノードでの PoW / PoS 動作確認:

```bash
uv run python scripts/verify_multinode.py
```

## 制限事項

本 P2P 実装は教育・試作向けです。本番利用には追加のセキュリティ監査が必要です。

| 項目 | 現状 |
|------|------|
| TLS / 暗号化 | オプトイン（`network.tls.enabled`、デフォルトは平文 `ws://`） |
| ピア認証 | 署名付き HELLO（`peer_auth.enabled`、デフォルト有効） |
| スパム・DoS 対策 | `max_peers`、`max_message_bytes`、IP/ピアレート制限、decode エラー切断 |
| gossip プロトコル | `transport: libp2p` で GossipSub 有効（デフォルトは WebSocket broadcast） |
| バッチ同期 | `chain_sync_batch_size` による複数ラウンド同期 |
| mDNS advertise | 実装済み（`mdns_advertise_enabled` で制御） |
| 合意種別 | 同一ネットワーク内で PoW / PoS は混在不可 |

## 関連テスト

| テストファイル | 内容 |
|---------------|------|
| `tests/unit/test_messages.py` | メッセージのエンコード・デコード |
| `tests/unit/test_network_settings.py` | ネットワーク・ノード設定のパース、ログレベル検証 |
| `tests/unit/test_p2p_server.py` | インバウンド `max_peers` 拒否 |
| `tests/unit/test_peer_listen.py` | decode エラースキップ・メッセージサイズ上限 |
| `tests/e2e/test_two_node_sync.py` | 2 ノード PoW 同期 |
| `tests/e2e/test_three_node_pow.py` | 3 ノード PoW |
| `tests/e2e/test_genesis_mismatch.py` | genesis 一致・不一致時の接続 |
| `tests/e2e/test_wss_two_node_sync.py` | WSS 有効時の 2 ノード同期 |
| `tests/unit/test_peer_auth.py` | 署名付き HELLO |
| `tests/unit/test_tls.py` | TLS 設定・スキーム判定 |
| `tests/unit/test_rate_limit.py` | レート制限 |
| `tests/unit/test_reconnect.py` | 再接続バックオフ |
| `tests/unit/test_batch_sync.py` | バッチ取得ロジック |

```bash
uv run pytest tests/unit/test_messages.py -v
uv run pytest tests/e2e -v -m slow
```

## 関連ドキュメント

- [README.md](../README.md) — プロジェクト全体の概要
- [CHANGELOG.md](../CHANGELOG.md) — v2.0.0 の変更履歴
- [config/default.yaml](../config/default.yaml) — デフォルト設定
