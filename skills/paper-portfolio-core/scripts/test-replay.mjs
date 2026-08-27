#!/usr/bin/env node

import assert from "node:assert/strict";
import {execFile} from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {promisify} from "node:util";
import {fileURLToPath} from "node:url";

const execFileAsync = promisify(execFile);
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "portfolio-replay-test-"));

const policy = {
  schema_version: "1.0.0",
  portfolio_id: "PF-DEMO",
  slug: "demo",
  display_name: "Demo",
  policy_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  currency: "INR",
  paper_trading: true,
  strategy: {label: "Moderate", explanation: "Test portfolio", risk_appetite: "Moderate", user_rules: ["Avoid excessive concentration"]},
  creation_request: {verbatim_prompt: "Create demo with ₹10 lakh", starting_capital: 1_000_000, market_cap_scope: ["Large", "Mid", "Small"], sector_scope: [], company_scope: [], research_first: true, proposal_first: true},
  asset_scope: ["Indian listed equity"],
  horizon: {kind: "rolling", years: 5},
  allocation_targets: {large: 0.6, mid: 0.25, small: 0.15, basis: "invested_equity_excluding_cash"},
  cash_policy: {minimum: 0, maximum: 0.2, tactical: true},
  warnings: {single_stock_weight: 0.1, sector_weight: 0.25, hard_caps: false},
  constraints: {long_only: true, whole_shares: true, leverage: false, derivatives: false, shorting: false},
  research_admission: {new_position_stance: "Investable Now", allow_cash_shortfall: true},
  benchmarks: {primary: "NIFTY 500 TRI", large: "NIFTY 100 TRI", mid: "NIFTY Midcap 150 TRI", small: "NIFTY Smallcap 250 TRI", return_basis: "total_return_index"},
  cost_policy: {statutory_costs: "dated_source_backed", slippage_bps_per_side: 10, personal_tax: false},
  approval_policy: {initial_trades: "explicit_proposal_approval", capital_deployment: "explicit_proposal_approval", rebalance: "explicit_proposal_approval", automatic_actions: false},
  user_exclusions: []
};

const base = {schema_version: "1.0.0", portfolio_id: "PF-DEMO", policy_version: 1};
const events = [
  {...base, event_id: "EV-CREATE", event_type: "portfolio_created", recorded_at: "2026-01-01T00:00:00Z", effective_at: "2026-01-01T00:00:00Z", display_name: "Demo"},
  {...base, event_id: "EV-CASH", event_type: "cash_flow", recorded_at: "2026-01-01T00:01:00Z", effective_at: "2026-01-01T00:01:00Z", flow_type: "Contribution", amount: 1_000_000},
  {...base, event_id: "EV-PROP1", event_type: "trade_proposal", recorded_at: "2026-01-02T00:00:00Z", effective_at: "2026-01-02T00:00:00Z", proposal_id: "PR-1", status: "Draft", trades: [{symbol: "DEMO", legal_name: "Demo Limited", side: "Buy", quantity: 100, price: 1000, price_as_of: "2026-01-01T10:00:00Z", price_source_id: "S001", fees: 100, slippage: 100, sector: "Industrials", market_cap_bucket: "Large", classification_vintage: "2026-H1", research_run_path: "research/demo/20260101T000000Z/", research_stance: "Investable Now"}], warnings: []},
  {...base, event_id: "EV-APP1", event_type: "proposal_status", recorded_at: "2026-01-02T00:01:00Z", effective_at: "2026-01-02T00:01:00Z", proposal_id: "PR-1", status: "Approved"},
  {...base, event_id: "EV-BUY", event_type: "trade_execution", recorded_at: "2026-01-02T00:02:00Z", effective_at: "2026-01-02T00:02:00Z", proposal_id: "PR-1", trade: {symbol: "DEMO", legal_name: "Demo Limited", side: "Buy", quantity: 100, price: 1000, price_as_of: "2026-01-01T10:00:00Z", price_source_id: "S001", fees: 100, slippage: 100, sector: "Industrials", market_cap_bucket: "Large", classification_vintage: "2026-H1", research_run_path: "research/demo/20260101T000000Z/", research_stance: "Investable Now"}},
  {...base, event_id: "EV-PRICE1", event_type: "price_snapshot", recorded_at: "2026-01-31T10:00:00Z", effective_at: "2026-01-31T10:00:00Z", observations: [{instrument: "DEMO", value: 1100, as_of: "2026-01-31T10:00:00Z", source_id: "S001"}], sources: [{source_id: "S001", title: "Demo equity snapshot", url: "https://example.com/equity", publisher: "Example Exchange", data_date: "2026-01-31T10:00:00Z", accessed_at: "2026-01-31T10:00:01Z"}]},
  {...base, event_id: "EV-BENCH", event_type: "benchmark_snapshot", recorded_at: "2026-01-31T10:01:00Z", effective_at: "2026-01-31T10:01:00Z", observations: [{instrument: "NIFTY 500 TRI", value: 20000, as_of: "2026-01-31T10:00:00Z", source_id: "S002"}], sources: [{source_id: "S002", title: "Demo TRI snapshot", url: "https://example.com/tri", publisher: "Example Index Provider", data_date: "2026-01-31T10:00:00Z", accessed_at: "2026-01-31T10:01:01Z"}]},
  {...base, event_id: "EV-THESIS", event_type: "thesis_snapshot", recorded_at: "2026-01-31T10:02:00Z", effective_at: "2026-01-31T10:02:00Z", symbol: "DEMO", research_run_path: "research/demo/20260101T000000Z/", thesis_status: "Intact", thesis: "Durable test economics", invalidation_triggers: ["Returns fall below hurdle"]},
  {...base, event_id: "EV-DIV", event_type: "dividend", recorded_at: "2026-02-10T10:00:00Z", effective_at: "2026-02-10T10:00:00Z", symbol: "DEMO", amount: 1000, payment_date: "2026-02-10"},
  {...base, event_id: "EV-PROP2", event_type: "trade_proposal", recorded_at: "2026-03-01T00:00:00Z", effective_at: "2026-03-01T00:00:00Z", proposal_id: "PR-2", status: "Draft", trades: [{symbol: "DEMO", legal_name: "Demo Limited", side: "Sell", quantity: 40, price: 1200, price_as_of: "2026-02-28T10:00:00Z", price_source_id: "S001", fees: 50, slippage: 50, sector: "Industrials", market_cap_bucket: "Large", classification_vintage: "2026-H1", research_run_path: "research/demo/20260101T000000Z/", research_stance: "Investable Now"}], warnings: []},
  {...base, event_id: "EV-APP2", event_type: "proposal_status", recorded_at: "2026-03-01T00:01:00Z", effective_at: "2026-03-01T00:01:00Z", proposal_id: "PR-2", status: "Approved"},
  {...base, event_id: "EV-SELL", event_type: "trade_execution", recorded_at: "2026-03-01T00:02:00Z", effective_at: "2026-03-01T00:02:00Z", proposal_id: "PR-2", trade: {symbol: "DEMO", legal_name: "Demo Limited", side: "Sell", quantity: 40, price: 1200, price_as_of: "2026-02-28T10:00:00Z", price_source_id: "S001", fees: 50, slippage: 50, sector: "Industrials", market_cap_bucket: "Large", classification_vintage: "2026-H1", research_run_path: "research/demo/20260101T000000Z/", research_stance: "Investable Now"}},
  {...base, event_id: "EV-PRICE2", event_type: "price_snapshot", recorded_at: "2026-03-01T10:00:00Z", effective_at: "2026-03-01T10:00:00Z", observations: [{instrument: "DEMO", value: 1200, as_of: "2026-03-01T10:00:00Z", source_id: "S001"}]}
];

try {
  const policyPath = path.join(tempDir, "policy.json");
  const ledgerPath = path.join(tempDir, "ledger.jsonl");
  const statePath = path.join(tempDir, "state.json");
  await fs.writeFile(policyPath, `${JSON.stringify(policy, null, 2)}\n`);
  await fs.writeFile(ledgerPath, `${events.map((event) => JSON.stringify(event)).join("\n")}\n`);
  await execFileAsync(process.execPath, [path.join(scriptDir, "replay-ledger.mjs"), "--policy", policyPath, "--ledger", ledgerPath, "--output", statePath]);
  const state = JSON.parse(await fs.readFile(statePath, "utf8"));
  assert.equal(state.summary.cash, 948700);
  assert.equal(state.summary.market_value, 72000);
  assert.equal(state.summary.portfolio_value, 1020700);
  assert.equal(state.holdings[0].shares, 60);
  assert.equal(state.holdings[0].open_cost, 60120);
  assert.equal(state.holdings[0].realized_pnl, 7820);
  assert.equal(state.holdings[0].unrealized_pnl, 11880);
  assert.equal(state.holdings[0].thesis_status, "Intact");
  assert.equal(state.transactions.length, 4);
  assert.ok(state.summary.xirr !== null);
  assert.equal(state.checks.filter((item) => item.status === "FAIL").length, 0);
  process.stdout.write("portfolio replay test: OK\n");
} finally {
  await fs.rm(tempDir, {recursive: true, force: true});
}
