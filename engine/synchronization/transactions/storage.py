"""JSON persistence for correction transactions."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .state import TransactionState
from .transaction import CorrectionTransaction

logger = logging.getLogger("hhip.synchronization.transactions.storage")

PathLike = Union[str, Path]

TERMINAL_STATES = {
    TransactionState.COMPLETED,
    TransactionState.FAILED,
    TransactionState.ROLLED_BACK,
}

UNFINISHED_STATES = {
    TransactionState.CREATED,
    TransactionState.SENT,
    TransactionState.APPLIED,
    TransactionState.VERIFYING,
}


class CorrectionTransactionStorage:
    """Persist correction transactions and manager bookkeeping to JSON.

    Layout::

        {base_dir}/correction_transactions.json
    """

    def __init__(self, base_dir: PathLike = "data/synchronization") -> None:
        self.base_dir = Path(base_dir)
        self.transactions_path = self.base_dir / "correction_transactions.json"
        self._lock = threading.Lock()

    def save_transaction(self, transaction: CorrectionTransaction) -> Path:
        """Upsert one transaction into the store."""
        data = self.load_raw()
        data.setdefault("transactions", {})[transaction.transaction_id] = transaction.to_dict()
        return self._write(data)

    def save_all(
        self,
        transactions: Mapping[str, CorrectionTransaction],
        *,
        accumulated_by_device: Optional[Mapping[str, float]] = None,
        last_correction_time: Optional[Mapping[str, int]] = None,
    ) -> Path:
        """Replace the full transaction snapshot."""
        data = {
            "transactions": {tid: txn.to_dict() for tid, txn in transactions.items()},
            "accumulated_by_device": dict(accumulated_by_device or {}),
            "last_correction_time": {
                str(k): int(v) for k, v in (last_correction_time or {}).items()
            },
        }
        return self._write(data)

    def load_all(self) -> dict[str, CorrectionTransaction]:
        raw = self.load_raw().get("transactions") or {}
        return {
            str(tid): CorrectionTransaction.from_dict(payload)
            for tid, payload in raw.items()
        }

    def load_unfinished(self) -> list[CorrectionTransaction]:
        return [
            txn
            for txn in self.load_all().values()
            if txn.state in UNFINISHED_STATES
        ]

    def load_bookkeeping(self) -> tuple[dict[str, float], dict[str, int]]:
        data = self.load_raw()
        accumulated = {
            str(k): float(v)
            for k, v in (data.get("accumulated_by_device") or {}).items()
        }
        last_time = {
            str(k): int(v)
            for k, v in (data.get("last_correction_time") or {}).items()
        }
        return accumulated, last_time

    def get(self, transaction_id: str) -> Optional[CorrectionTransaction]:
        return self.load_all().get(transaction_id)

    def load_raw(self) -> dict[str, Any]:
        if not self.transactions_path.exists():
            return {
                "transactions": {},
                "accumulated_by_device": {},
                "last_correction_time": {},
            }
        with self.transactions_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {
                "transactions": {},
                "accumulated_by_device": {},
                "last_correction_time": {},
            }
        data.setdefault("transactions", {})
        data.setdefault("accumulated_by_device", {})
        data.setdefault("last_correction_time", {})
        return data

    def _write(self, data: Mapping[str, Any]) -> Path:
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            with self.transactions_path.open("w", encoding="utf-8") as fh:
                json.dump(dict(data), fh, indent=2, sort_keys=True)
                fh.write("\n")
        logger.debug("[TXN STORAGE] Saved → %s", self.transactions_path)
        return self.transactions_path
