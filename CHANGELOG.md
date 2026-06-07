# Changelog

## 2.1.0

### Added

- Chain persistence under `node.data_dir` (`chain.json`, `meta.json`, `genesis_stakes.json`)
- PoS private key persistence (`keys/node.pem`, mode 0600)
- `ChainStore` with atomic writes and chain checksum verification
- `PersistenceSettings` in `config/default.yaml`
- `SignatureManager.export_private_key()` / `import_private_key()`
- `BlockChain.replace_chain()` restores PoS validator state via `sync_validators_from_chain`
- Unit and integration tests for persistence and node restart

### Changed

- `Node` loads persisted state on startup and saves on block add, fork resolution, and stop
- Persisted `node_id` and `genesis_stakes` take precedence over config/constructor on restart

## 2.0.0

### Added

- Pluggable consensus: Proof of Work (PoW) and Proof of Stake (PoS)
- P2P networking over WebSockets (HELLO, PEERS, GET_CHAIN, NEW_BLOCK, PING/PONG)
- `Node` orchestrator for multi-node operation
- `verify_chain()` for chain integrity validation
- Configuration via `config/default.yaml` and `EASYBLOCKCHAIN_CONFIG`
- `pyproject.toml`, GitHub Actions CI, `tests/` directory structure
- CLI example: `examples/run_node.py`

### Changed

- `BlockChain` accepts optional `consensus` parameter
- Block header extended with consensus-specific fields
- Version bumped to 2.0.0

### Notes

- v1 compatibility: `BlockChain()` without consensus retains legacy instant-add behavior
- Distributed mode recommended via `Node(config_path=...)`

## 1.0.0

- Initial release with basic blockchain and RSA signatures
