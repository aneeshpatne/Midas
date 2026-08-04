"""Transactions and market prices repositories."""

from __future__ import annotations

from midas.db.helpers import new_id, now_ms
from midas.db.models import (
    CreateTransactionInput,
    MarketPrice,
    Transaction,
    TransactionType,
    UpsertMarketPriceInput,
)
from midas.db.repositories.base import conn, fetchall_dicts, fetchone_dict


class TransactionsRepository:
    def find_by_id(self, id_: str) -> Transaction | None:
        cur = conn().execute("SELECT * FROM transactions WHERE id = ?", (id_,))
        row = fetchone_dict(cur)
        return Transaction.model_validate(row) if row else None

    def list_by_portfolio(
        self,
        portfolio_id: str,
        *,
        type_: TransactionType | None = None,
        security_id: str | None = None,
        investment_case_id: str | None = None,
        account_id: str | None = None,
        from_executed_at: int | None = None,
        to_executed_at: int | None = None,
    ) -> list[Transaction]:
        clauses = ["portfolio_id = ?"]
        params: list[object] = [portfolio_id]
        if type_:
            clauses.append("type = ?")
            params.append(type_)
        if security_id:
            clauses.append("security_id = ?")
            params.append(security_id)
        if investment_case_id:
            clauses.append("investment_case_id = ?")
            params.append(investment_case_id)
        if account_id:
            clauses.append("account_id = ?")
            params.append(account_id)
        if from_executed_at is not None:
            clauses.append("executed_at >= ?")
            params.append(from_executed_at)
        if to_executed_at is not None:
            clauses.append("executed_at <= ?")
            params.append(to_executed_at)
        cur = conn().execute(
            f"""
            SELECT * FROM transactions
            WHERE {" AND ".join(clauses)}
            ORDER BY executed_at DESC, created_at DESC
            """,
            params,
        )
        return [Transaction.model_validate(r) for r in fetchall_dicts(cur)]

    def list_by_security(self, security_id: str) -> list[Transaction]:
        cur = conn().execute(
            """
            SELECT * FROM transactions
            WHERE security_id = ?
            ORDER BY executed_at DESC, created_at DESC
            """,
            (security_id,),
        )
        return [Transaction.model_validate(r) for r in fetchall_dicts(cur)]

    def list_by_investment_case(self, investment_case_id: str) -> list[Transaction]:
        cur = conn().execute(
            """
            SELECT * FROM transactions
            WHERE investment_case_id = ?
            ORDER BY executed_at DESC, created_at DESC
            """,
            (investment_case_id,),
        )
        return [Transaction.model_validate(r) for r in fetchall_dicts(cur)]

    def sum_cash_balance_paise(self, portfolio_id: str) -> int:
        cur = conn().execute(
            """
            SELECT COALESCE(SUM(cash_effect_paise), 0) AS cash_balance_paise
            FROM transactions WHERE portfolio_id = ?
            """,
            (portfolio_id,),
        )
        row = fetchone_dict(cur)
        return int(row["cash_balance_paise"] if row else 0)

    def sum_net_contributed_capital_paise(self, portfolio_id: str) -> int:
        cur = conn().execute(
            """
            SELECT COALESCE(SUM(cash_effect_paise), 0) AS net_contributed_paise
            FROM transactions
            WHERE portfolio_id = ? AND type IN ('DEPOSIT', 'WITHDRAWAL')
            """,
            (portfolio_id,),
        )
        row = fetchone_dict(cur)
        return int(row["net_contributed_paise"] if row else 0)

    def sum_deposits_paise(self, portfolio_id: str) -> int:
        cur = conn().execute(
            """
            SELECT COALESCE(SUM(cash_effect_paise), 0) AS total_deposits_paise
            FROM transactions
            WHERE portfolio_id = ? AND type = 'DEPOSIT'
            """,
            (portfolio_id,),
        )
        row = fetchone_dict(cur)
        return int(row["total_deposits_paise"] if row else 0)

    def sum_withdrawals_paise(self, portfolio_id: str) -> int:
        cur = conn().execute(
            """
            SELECT COALESCE(SUM(ABS(cash_effect_paise)), 0)
              AS total_withdrawals_paise
            FROM transactions
            WHERE portfolio_id = ? AND type = 'WITHDRAWAL'
            """,
            (portfolio_id,),
        )
        row = fetchone_dict(cur)
        return int(row["total_withdrawals_paise"] if row else 0)

    def create(
        self, input_: CreateTransactionInput, *, cash_effect_paise: int
    ) -> Transaction:
        id_ = input_.id or new_id()
        ts = now_ms()
        conn().execute(
            """
            INSERT INTO transactions (
              id, portfolio_id, account_id, security_id, investment_case_id,
              type, quantity_micros, price_paise, gross_amount_paise,
              fees_paise, taxes_paise, net_amount_paise, cash_effect_paise,
              currency, exchange_rate_micros, executed_at, settlement_date,
              external_reference, notes, created_at
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                id_,
                input_.portfolio_id,
                input_.account_id,
                input_.security_id,
                input_.investment_case_id,
                input_.type,
                input_.quantity_micros,
                input_.price_paise,
                input_.gross_amount_paise,
                input_.fees_paise,
                input_.taxes_paise,
                input_.net_amount_paise,
                cash_effect_paise,
                input_.currency or "INR",
                input_.exchange_rate_micros,
                input_.executed_at,
                input_.settlement_date,
                input_.external_reference,
                input_.notes,
                ts,
            ),
        )
        conn().commit()
        created = self.find_by_id(id_)
        if not created:
            raise RuntimeError(f"Failed to create transaction: {id_}")
        return created

    def delete(self, id_: str) -> bool:
        cur = conn().execute("DELETE FROM transactions WHERE id = ?", (id_,))
        conn().commit()
        return cur.rowcount > 0


class MarketPricesRepository:
    def find(self, security_id: str, price_date: str) -> MarketPrice | None:
        cur = conn().execute(
            """
            SELECT * FROM market_prices
            WHERE security_id = ? AND price_date = ?
            """,
            (security_id, price_date),
        )
        row = fetchone_dict(cur)
        return MarketPrice.model_validate(row) if row else None

    def list_by_security(
        self, security_id: str, *, limit: int = 500
    ) -> list[MarketPrice]:
        cur = conn().execute(
            """
            SELECT * FROM market_prices
            WHERE security_id = ?
            ORDER BY price_date DESC
            LIMIT ?
            """,
            (security_id, limit),
        )
        return [MarketPrice.model_validate(r) for r in fetchall_dicts(cur)]

    def latest(self, security_id: str) -> MarketPrice | None:
        cur = conn().execute(
            """
            SELECT * FROM market_prices
            WHERE security_id = ?
            ORDER BY price_date DESC
            LIMIT 1
            """,
            (security_id,),
        )
        row = fetchone_dict(cur)
        return MarketPrice.model_validate(row) if row else None

    def upsert(self, input_: UpsertMarketPriceInput) -> MarketPrice:
        ts = input_.captured_at if input_.captured_at is not None else now_ms()
        conn().execute(
            """
            INSERT INTO market_prices (
              security_id, price_date, price_paise, currency, source, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(security_id, price_date) DO UPDATE SET
              price_paise = excluded.price_paise,
              currency = excluded.currency,
              source = excluded.source,
              captured_at = excluded.captured_at
            """,
            (
                input_.security_id,
                input_.price_date,
                input_.price_paise,
                input_.currency or "INR",
                input_.source,
                ts,
            ),
        )
        conn().commit()
        found = self.find(input_.security_id, input_.price_date)
        if not found:
            raise RuntimeError(
                f"Failed to upsert market price: "
                f"{input_.security_id} {input_.price_date}"
            )
        return found

    def delete(self, security_id: str, price_date: str) -> bool:
        cur = conn().execute(
            """
            DELETE FROM market_prices
            WHERE security_id = ? AND price_date = ?
            """,
            (security_id, price_date),
        )
        conn().commit()
        return cur.rowcount > 0


transactions_repository = TransactionsRepository()
market_prices_repository = MarketPricesRepository()
