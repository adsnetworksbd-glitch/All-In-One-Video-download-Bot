import hashlib, time
from typing import Optional
from database.firebase import firebase_manager, DatabaseReadError, DatabaseWriteError
from logger import logger

class InsufficientCreditsError(Exception): pass

class CreditRepository:
    def __init__(self): self.fb = firebase_manager

    def _get_safe_ref_key(self, reference_id: str) -> str:
        raw = str(reference_id).strip()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def record_transaction(self, telegram_user_id: int, amount: int, balance_after: int, tx_type: str, reference_id: str, reason: str, tx_id: Optional[str] = None) -> str:
        transaction_id = tx_id or f"tx_{int(time.time() * 1000)}_{telegram_user_id}"
        record = {
            "transaction_id": transaction_id, "telegram_user_id": int(telegram_user_id),
            "amount": int(amount), "balance_after": int(balance_after), "type": str(tx_type),
            "reference_id": str(reference_id), "reason": str(reason), "created_at": int(time.time() * 1000)
        }
        self.fb.safe_set(f"credit_transactions/{transaction_id}", record)
        return transaction_id

    def reserve_or_deduct_credits(self, telegram_user_id: int, amount: int, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Amount must be positive.")
        safe_op_key = self._get_safe_ref_key(f"debit_{reference_id}")
        deterministic_tx_id = f"tx_debit_{safe_op_key}"
        user_path = f"users/{telegram_user_id}"
        now = int(time.time() * 1000)
        state = {"already_debited": False, "err": None}

        def debit_txn(curr_user):
            if curr_user is None:
                state["err"] = "USER_NOT_FOUND"
                return None
            applied = curr_user.setdefault("applied_debits", {})
            if safe_op_key in applied:
                state["already_debited"] = True
                return curr_user
            curr_bal = curr_user.get("credit_balance")
            if curr_bal is None or curr_bal < amount:
                state["err"] = "INSUFFICIENT"
                state["val"] = curr_bal or 0
                return None
            curr_user["credit_balance"] = curr_bal - amount
            applied[safe_op_key] = {"amount": amount, "at": now, "tx_id": deterministic_tx_id, "ledger_written": False}
            return curr_user

        updated = self.fb.run_transaction(user_path, debit_txn)
        if state["err"]:
            if state["err"] == "INSUFFICIENT": raise InsufficientCreditsError(f"Required {amount}, available {state.get('val', 0)}")
            raise DatabaseWriteError(f"Transaction aborted: {state['err']}")

        final_bal = int(updated.get("credit_balance", 0))
        if not state["already_debited"]:
            self.record_transaction(telegram_user_id, -amount, final_bal, "DOWNLOAD_DEBIT", reference_id, reason, deterministic_tx_id)
            try: self.fb.safe_update(f"users/{telegram_user_id}/applied_debits/{safe_op_key}", {"ledger_written": True})
            except Exception: pass
        return final_bal

    def refund_credits(self, telegram_user_id: int, amount: int, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Amount must be positive.")
        safe_ref = self._get_safe_ref_key(reference_id)
        claim_path = f"refund_claims/{safe_ref}"
        now = int(time.time() * 1000)
        deterministic_tx_id = f"tx_refund_{safe_ref}"
        decision = {"action": "PROCEED"}

        def claim_txn(curr):
            if curr is None:
                return {"reference_id": str(reference_id), "telegram_user_id": int(telegram_user_id), "amount": int(amount), "status": "PENDING", "tx_id": deterministic_tx_id, "created_at": now}
            if curr.get("telegram_user_id") != telegram_user_id or curr.get("amount") != amount:
                decision["action"] = "MISMATCH"
                return curr
            if curr.get("status") == "COMPLETED":
                decision["action"] = "ALREADY_COMPLETED"
                return curr
            decision["action"] = "RECOVER_PENDING"
            return curr

        self.fb.run_transaction(claim_path, claim_txn)
        if decision["action"] == "MISMATCH": raise ValueError(f"Parameter mismatch for refund {reference_id}")
        if decision["action"] == "ALREADY_COMPLETED":
            bal = self.fb.safe_get(f"users/{telegram_user_id}/credit_balance")
            if bal is None: raise DatabaseReadError(f"Could not read balance for {telegram_user_id}")
            return int(bal)

        user_path = f"users/{telegram_user_id}"
        state = {"need_ledger": True}

        def balance_marker_txn(curr_user):
            if curr_user is None: raise DatabaseReadError(f"User {telegram_user_id} not found.")
            applied = curr_user.setdefault("applied_refunds", {})
            if safe_ref in applied:
                if applied[safe_ref].get("ledger_written") is True: state["need_ledger"] = False
                return curr_user
            curr_user["credit_balance"] = (curr_user.get("credit_balance") or 0) + amount
            applied[safe_ref] = {"amount": amount, "at": now, "tx_id": deterministic_tx_id, "ledger_written": False}
            return curr_user

        updated = self.fb.run_transaction(user_path, balance_marker_txn)
        final_bal = int(updated.get("credit_balance", 0))

        if state["need_ledger"]:
            self.record_transaction(telegram_user_id, amount, final_bal, "DOWNLOAD_REFUND", reference_id, reason, deterministic_tx_id)
            try: self.fb.safe_update(f"users/{telegram_user_id}/applied_refunds/{safe_ref}", {"ledger_written": True})
            except Exception: pass

        self.fb.safe_update(claim_path, {"status": "COMPLETED", "completed_at": int(time.time() * 1000), "balance_after": final_bal})
        return final_bal

    def add_reward_credits(self, telegram_user_id: int, amount: int, reward_type: str, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Reward amount must be positive.")
        safe_ref = self._get_safe_ref_key(f"reward_{reference_id}")
        user_path = f"users/{telegram_user_id}"
        state = {"already_rewarded": False, "err": None}
        now = int(time.time() * 1000)

        def reward_txn(curr_user):
            if curr_user is None:
                state["err"] = "USER_NOT_FOUND"
                return None
            applied = curr_user.setdefault("applied_rewards", {})
            if safe_ref in applied:
                state["already_rewarded"] = True
                return curr_user
            curr_user["credit_balance"] = (curr_user.get("credit_balance") or 0) + amount
            applied[safe_ref] = {"amount": amount, "at": now}
            return curr_user

        updated = self.fb.run_transaction(user_path, reward_txn)
        if state["err"] == "USER_NOT_FOUND":
            raise DatabaseReadError(f"User {telegram_user_id} not found.")

        new_bal = int(updated.get("credit_balance", 0))
        if not state["already_rewarded"]:
            self.record_transaction(telegram_user_id, amount, new_bal, reward_type, reference_id, reason, f"tx_reward_{safe_ref}")
        return new_bal

credit_repo = CreditRepository()