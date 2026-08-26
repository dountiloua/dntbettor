"""
Autonomous Financial Accounting & Expense Management Engine.
Tracks bankroll, calculates operating bills (API, VPS, proxies),
manages profit distribution (User Wage vs Bills vs Compounding),
handles wallet payouts, and enforces capital preservation circuit breakers.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel


class FinancialConfig(BaseModel):
    initial_budget: float = 100.00
    monthly_vps_cost: float = 6.00
    monthly_api_cost: float = 15.00
    monthly_proxy_cost: float = 5.00
    
    # Allocation Percentages (must sum to 1.0)
    user_wage_share: float = 0.40       # 40% to your monthly wage
    bankroll_reinvest_share: float = 0.30  # 30% reinvested to scale bets
    bills_reserve_share: float = 0.20   # 20% reserved for server & API costs
    emergency_buffer_share: float = 0.10 # 10% emergency buffer

    # Circuit Breaker: Stop live betting if bankroll drops below this percentage of initial
    drawdown_circuit_breaker: float = 0.20  # 20% max drawdown


class FinancialManager:
    def __init__(self, db_path: Optional[Path] = None, config: Optional[FinancialConfig] = None):
        self.config = config or FinancialConfig()
        self.db_path = db_path or (Path(__file__).resolve().parent / "browser_data" / "financial_ledger.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for trades, expenses, payouts, and ledger."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Bets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT,
                    match_name TEXT,
                    market TEXT,
                    stake_amount REAL,
                    odds REAL,
                    outcome TEXT DEFAULT 'PENDING',  -- 'WON', 'LOST', 'VOID', 'PENDING'
                    profit_loss REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Financial buckets / ledger state
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ledger_state (
                    id INTEGER PRIMARY KEY,
                    current_bankroll REAL,
                    user_wage_pool REAL,
                    bills_reserve_pool REAL,
                    emergency_pool REAL,
                    total_profit_generated REAL,
                    total_bills_paid REAL,
                    total_payouts_completed REAL DEFAULT 0.0,
                    circuit_breaker_tripped INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Operating expenses log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operating_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_type TEXT,  -- 'API', 'VPS', 'PROXY', 'NETWORK_FEE'
                    amount REAL,
                    paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Payout withdrawals history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payout_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL,
                    currency TEXT,
                    destination_address TEXT,
                    status TEXT DEFAULT 'PROCESSED', -- 'PROCESSED', 'PENDING'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Initialize ledger state if empty
            cursor.execute("SELECT COUNT(*) FROM ledger_state")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO ledger_state (
                        id, current_bankroll, user_wage_pool, bills_reserve_pool, 
                        emergency_pool, total_profit_generated, total_bills_paid, total_payouts_completed, circuit_breaker_tripped
                    ) VALUES (1, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
                """, (self.config.initial_budget,))
            conn.commit()

    def get_status(self) -> Dict[str, Any]:
        """Returns the current financial health, bankroll, bills reserve, and user wage balance."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_bankroll, user_wage_pool, bills_reserve_pool, emergency_pool, total_profit_generated, total_bills_paid, circuit_breaker_tripped FROM ledger_state WHERE id = 1")
            row = cursor.fetchone()
            
            monthly_bills = self.config.monthly_vps_cost + self.config.monthly_api_cost + self.config.monthly_proxy_cost
            
            return {
                "current_bankroll": round(row[0], 2),
                "user_wage_pool": round(row[1], 2),
                "bills_reserve_pool": round(row[2], 2),
                "emergency_pool": round(row[3], 2),
                "total_profit_generated": round(row[4], 2),
                "total_bills_paid": round(row[5], 2),
                "circuit_breaker_tripped": bool(row[6]),
                "estimated_monthly_bills": monthly_bills,
                "bills_coverage_months": round(row[2] / monthly_bills, 1) if monthly_bills > 0 else 0.0
            }

    def get_recent_bet_counts(self) -> Dict[str, int]:
        """Returns the number of bets placed in the last 24 hours and last 7 days."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bets WHERE created_at >= datetime('now', '-24 hours')")
            daily_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM bets WHERE created_at >= datetime('now', '-7 days')")
            weekly_count = cursor.fetchone()[0]
            return {
                "daily_bets": daily_count,
                "weekly_bets": weekly_count
            }

    def can_place_new_bet(self, max_daily: int = 4, max_weekly: int = 25) -> Tuple[bool, str]:
        """Verifies that daily and weekly bet quotas have not been exceeded."""
        counts = self.get_recent_bet_counts()
        if counts["daily_bets"] >= max_daily:
            return False, f"Daily bet ceiling reached ({counts['daily_bets']}/{max_daily} bets in last 24h)."
        if counts["weekly_bets"] >= max_weekly:
            return False, f"Weekly bet ceiling reached ({counts['weekly_bets']}/{max_weekly} bets in last 7 days)."
        return True, "OK"

    def record_bet_placement(self, match_id: str | int, match_name: str, market: str, stake_amount: float, odds: float) -> int:
        """Records a new placed bet in the ledger with its dynamic stake amount."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bets (match_id, match_name, market, stake_amount, odds, outcome, profit_loss)
                VALUES (?, ?, ?, ?, ?, 'PENDING', 0.0)
            """, (str(match_id), match_name, market, stake_amount, odds))
            conn.commit()
            return cursor.lastrowid

    def record_bet_outcome(self, bet_id: int, outcome: str, profit_loss: float):
        """
        Records the outcome of a bet ('WON' or 'LOST') and executes the profit distribution waterfall.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE bets SET outcome = ?, profit_loss = ? WHERE id = ?", (outcome, profit_loss, bet_id))
            
            cursor.execute("SELECT current_bankroll, user_wage_pool, bills_reserve_pool, emergency_pool, total_profit_generated FROM ledger_state WHERE id = 1")
            state = cursor.fetchone()
            bankroll, wage_pool, bills_pool, emergency_pool, total_profit = state

            if profit_loss > 0:
                # Distribute profits across 4 buckets
                user_share = profit_loss * self.config.user_wage_share
                reinvest_share = profit_loss * self.config.bankroll_reinvest_share
                bills_share = profit_loss * self.config.bills_reserve_share
                emergency_share = profit_loss * self.config.emergency_buffer_share

                new_bankroll = bankroll + reinvest_share
                new_wage_pool = wage_pool + user_share
                new_bills_pool = bills_pool + bills_share
                new_emergency = emergency_pool + emergency_share
                new_total_profit = total_profit + profit_loss
            else:
                # Loss is deducted from bankroll
                new_bankroll = bankroll + profit_loss
                new_wage_pool = wage_pool
                new_bills_pool = bills_pool
                new_emergency = emergency_pool
                new_total_profit = total_profit

            # Check Circuit Breaker
            circuit_breaker = 1 if new_bankroll <= (self.config.initial_budget * (1.0 - self.config.drawdown_circuit_breaker)) else 0

            cursor.execute("""
                UPDATE ledger_state SET
                    current_bankroll = ?,
                    user_wage_pool = ?,
                    bills_reserve_pool = ?,
                    emergency_pool = ?,
                    total_profit_generated = ?,
                    circuit_breaker_tripped = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (new_bankroll, new_wage_pool, new_bills_pool, new_emergency, new_total_profit, circuit_breaker))
            conn.commit()

    def deduct_operating_bill(self, bill_type: str, amount: float) -> bool:
        """Deducts an operating expense (API / VPS / Proxy) from the bills reserve."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bills_reserve_pool, total_bills_paid FROM ledger_state WHERE id = 1")
            bills_pool, total_paid = cursor.fetchone()

            if bills_pool >= amount:
                new_pool = bills_pool - amount
                cursor.execute("UPDATE ledger_state SET bills_reserve_pool = ?, total_bills_paid = ? WHERE id = 1", (new_pool, total_paid + amount))
                cursor.execute("INSERT INTO operating_expenses (expense_type, amount) VALUES (?, ?)", (bill_type, amount))
                conn.commit()
                return True
            else:
                print(f"[FinancialManager] ⚠️ Bills reserve pool (${bills_pool:.2f}) insufficient to pay ${amount:.2f} for {bill_type}.")
                return False

    def process_user_wage_payout(self, destination_address: str, currency: str, amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Deducts available user wage funds and records a payout transaction to the user's linked wallet.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_wage_pool, total_payouts_completed FROM ledger_state WHERE id = 1")
            wage_pool, total_payouts = cursor.fetchone()
            
            payout_amount = amount if (amount is not None and amount > 0) else wage_pool

            if payout_amount <= 0:
                return {"success": False, "error": "No wage funds available to withdraw ($0.00)."}
            if payout_amount > wage_pool:
                return {"success": False, "error": f"Requested amount (${payout_amount:.2f}) exceeds available pool (${wage_pool:.2f})."}

            new_wage_pool = wage_pool - payout_amount
            new_total_payouts = total_payouts + payout_amount

            cursor.execute("""
                UPDATE ledger_state SET
                    user_wage_pool = ?,
                    total_payouts_completed = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (new_wage_pool, new_total_payouts))

            cursor.execute("""
                INSERT INTO payout_history (amount, currency, destination_address, status)
                VALUES (?, ?, ?, 'PROCESSED')
            """, (payout_amount, currency, destination_address))
            conn.commit()

            return {
                "success": True,
                "amount": payout_amount,
                "currency": currency,
                "destination_address": destination_address,
                "remaining_wage_pool": round(new_wage_pool, 2)
            }
