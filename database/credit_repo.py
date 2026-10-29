import time, uuid
from database.firebase import firebase_manager

class CreditRepository:
    def __init__(self): self.fb = firebase_manager

    def record_tx(self, tg_id, amt, bal, t_type, r_id, reason):
        tx_id = str(uuid.uuid4())
        self.fb.safe_set(f"credit_transactions/{tx_id}", {
            "transaction_id": tx_id, "telegram_user_id": tg_id, "amount": amt,
            "balance_after": bal, "type": t_type, "reference_id": r_id, "reason": reason,
            "created_at": int(time.time() * 1000)
        })

    def reserve_or_deduct_credits(self, tg_id: int, amt: int, r_id: str, reason: str):
        path = f"users/{tg_id}/credit_balance"
        err = {}
        def txn(curr):
            if curr is None or curr < amt:
                err["err"] = curr or 0
                return None
            return curr - amt
        new_bal = self.fb.run_transaction(path, txn)
        if "err" in err: raise ValueError(f"Insufficient balance. Required: {amt}, Available: {err['err']}")
        self.record_tx(tg_id, -amt, new_bal, "DOWNLOAD_DEBIT", r_id, reason)
        return new_bal

    def refund_credits(self, tg_id: int, amt: int, r_id: str, reason: str):
        if amt <= 0: return 0
        new_bal = self.fb.run_transaction(f"users/{tg_id}/credit_balance", lambda c: (c or 0) + amt)
        self.record_tx(tg_id, amt, new_bal, "DOWNLOAD_REFUND", r_id, reason)
        return new_bal

    def add_reward_credits(self, tg_id: int, amt: int, r_type: str, r_id: str, reason: str):
        if amt <= 0: return 0
        new_bal = self.fb.run_transaction(f"users/{tg_id}/credit_balance", lambda c: (c or 0) + amt)
        self.record_tx(tg_id, amt, new_bal, r_type, r_id, reason)
        return new_bal