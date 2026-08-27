#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

function fail(message) {
  throw new Error(message);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key?.startsWith("--") || value === undefined) fail("Use --policy, --ledger, and --output arguments");
    args[key.slice(2)] = value;
  }
  if (!args.policy || !args.ledger || !args.output) fail("Missing --policy, --ledger, or --output");
  return args;
}

function round(value, digits = 8) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const scale = 10 ** digits;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}

function sortEvents(events) {
  return [...events].sort((a, b) =>
    a.effective_at.localeCompare(b.effective_at)
    || a.recorded_at.localeCompare(b.recorded_at)
    || a.event_id.localeCompare(b.event_id));
}

function xnpv(rate, flows) {
  const origin = new Date(flows[0].date).getTime();
  return flows.reduce((sum, flow) => {
    const years = (new Date(flow.date).getTime() - origin) / 31_557_600_000;
    return sum + flow.amount / ((1 + rate) ** years);
  }, 0);
}

function xirr(flows) {
  if (flows.length < 2 || !flows.some((x) => x.amount < 0) || !flows.some((x) => x.amount > 0)) return null;
  let low = -0.9999;
  let high = 10;
  let lowValue = xnpv(low, flows);
  let highValue = xnpv(high, flows);
  for (let attempts = 0; lowValue * highValue > 0 && attempts < 8; attempts += 1) {
    high *= 10;
    highValue = xnpv(high, flows);
  }
  if (!Number.isFinite(lowValue) || !Number.isFinite(highValue) || lowValue * highValue > 0) return null;
  for (let i = 0; i < 160; i += 1) {
    const mid = (low + high) / 2;
    const value = xnpv(mid, flows);
    if (Math.abs(value) < 1e-8) return mid;
    if (lowValue * value <= 0) {
      high = mid;
      highValue = value;
    } else {
      low = mid;
      lowValue = value;
    }
  }
  return (low + high) / 2;
}

function createPosition(trade) {
  return {
    symbol: trade.symbol,
    legal_name: trade.legal_name,
    sector: trade.sector ?? null,
    market_cap_bucket: trade.market_cap_bucket ?? "Unknown",
    classification_vintage: trade.classification_vintage ?? null,
    lots: [],
    realized_pnl: 0,
    thesis_status: "Needs Evidence",
    thesis_date: null,
    research_run_path: trade.research_run_path ?? null,
  };
}

function positionShares(position) {
  return position.lots.reduce((sum, lot) => sum + lot.quantity, 0);
}

function positionCost(position) {
  return position.lots.reduce((sum, lot) => sum + lot.cost, 0);
}

function consumeFifo(position, quantity, netProceeds) {
  if (positionShares(position) < quantity) fail(`Sell exceeds shares held for ${position.symbol}`);
  let remaining = quantity;
  let removedCost = 0;
  while (remaining > 0) {
    const lot = position.lots[0];
    const used = Math.min(remaining, lot.quantity);
    const usedCost = lot.cost * (used / lot.quantity);
    removedCost += usedCost;
    lot.quantity -= used;
    lot.cost -= usedCost;
    remaining -= used;
    if (lot.quantity === 0) position.lots.shift();
  }
  position.realized_pnl += netProceeds - removedCost;
}

function applyCorrections(events) {
  const corrections = new Map();
  for (const event of events) {
    if (event.event_type === "correction") {
      if (corrections.has(event.supersedes_event_id)) fail(`Multiple corrections for ${event.supersedes_event_id}`);
      corrections.set(event.supersedes_event_id, event);
    }
  }
  const ids = new Set(events.map((event) => event.event_id));
  for (const target of corrections.keys()) if (!ids.has(target)) fail(`Correction target not found: ${target}`);
  const output = [];
  for (const event of events) {
    if (event.event_type === "correction") continue;
    const correction = corrections.get(event.event_id);
    if (!correction) {
      output.push(event);
      continue;
    }
    const replacement = correction.replacement;
    if (!replacement || typeof replacement !== "object") fail(`Correction ${correction.event_id} has no replacement event`);
    output.push({
      ...replacement,
      schema_version: replacement.schema_version ?? event.schema_version,
      event_id: correction.event_id,
      portfolio_id: replacement.portfolio_id ?? event.portfolio_id,
      recorded_at: correction.recorded_at,
      effective_at: replacement.effective_at ?? event.effective_at,
      policy_version: replacement.policy_version ?? correction.policy_version,
      notes: `Correction of ${event.event_id}: ${correction.reason}`,
    });
  }
  return output;
}

async function main() {
  const args = parseArgs(process.argv);
  const policy = JSON.parse(await fs.readFile(args.policy, "utf8"));
  const ledgerText = await fs.readFile(args.ledger, "utf8");
  const parsedEvents = ledgerText.split(/\r?\n/).filter(Boolean).map((line, index) => {
    try { return JSON.parse(line); } catch (error) { fail(`Invalid ledger JSON on line ${index + 1}: ${error.message}`); }
  });
  const duplicateIds = parsedEvents.map((x) => x.event_id).filter((id, index, all) => all.indexOf(id) !== index);
  if (duplicateIds.length) fail(`Duplicate event IDs: ${[...new Set(duplicateIds)].join(", ")}`);

  const events = sortEvents(applyCorrections(parsedEvents));
  const positions = new Map();
  const proposals = new Map();
  const prices = new Map();
  const theses = new Map();
  const sources = new Map();
  const transactions = [];
  const performance = [];
  const benchmarkObservations = [];
  const externalFlows = [];
  let cash = 0;
  let contributions = 0;
  let withdrawals = 0;
  let units = 0;
  const initialNav = 100;

  const investedMarketValue = () => [...positions.values()].reduce((sum, position) => {
    const price = prices.get(position.symbol)?.value;
    return sum + (price === undefined ? 0 : positionShares(position) * price);
  }, 0);
  const totalValue = () => cash + investedMarketValue();

  for (const event of events) {
    if (event.portfolio_id !== policy.portfolio_id) fail(`Portfolio mismatch in ${event.event_id}`);
    for (const source of event.sources ?? []) {
      if (sources.has(source.source_id) && JSON.stringify(sources.get(source.source_id)) !== JSON.stringify(source)) {
        fail(`Conflicting source ID ${source.source_id}`);
      }
      sources.set(source.source_id, source);
    }

    const valueBefore = totalValue();
    const navBefore = units > 0 ? valueBefore / units : initialNav;

    switch (event.event_type) {
      case "portfolio_created":
        break;
      case "cash_flow": {
        const signed = event.flow_type === "Contribution" ? event.amount : -event.amount;
        if (signed < 0 && cash + signed < -1e-8) fail(`Withdrawal creates negative cash in ${event.event_id}`);
        if (signed > 0) {
          contributions += signed;
          units += signed / navBefore;
          externalFlows.push({date: event.effective_at, amount: -signed});
        } else {
          withdrawals += -signed;
          if (units <= 0) fail(`Withdrawal has no portfolio units in ${event.event_id}`);
          units -= (-signed) / navBefore;
          externalFlows.push({date: event.effective_at, amount: -signed});
        }
        cash += signed;
        transactions.push({event_id: event.event_id, date: event.effective_at, type: event.flow_type, symbol: null, quantity: null, price: null, gross: signed, costs: 0, net_cash: signed, proposal_id: null, source_ids: event.source_ids ?? []});
        break;
      }
      case "trade_proposal":
        if (proposals.has(event.proposal_id)) fail(`Duplicate proposal ID ${event.proposal_id}`);
        proposals.set(event.proposal_id, {
          status: event.status,
          event_id: event.event_id,
          remaining: new Map(event.trades.map((trade) => [`${trade.side}:${trade.symbol}`, trade.quantity])),
        });
        break;
      case "proposal_status": {
        const proposal = proposals.get(event.proposal_id);
        if (!proposal) fail(`Unknown proposal ${event.proposal_id}`);
        if (proposal.status === "Executed") fail(`Proposal already executed: ${event.proposal_id}`);
        if (event.status === "Executed" && [...proposal.remaining.values()].some((quantity) => quantity !== 0)) fail(`Proposal ${event.proposal_id} is not fully executed`);
        proposal.status = event.status;
        break;
      }
      case "trade_execution": {
        const proposal = proposals.get(event.proposal_id);
        if (!proposal || !["Approved", "Executed"].includes(proposal.status)) fail(`Unapproved execution for ${event.proposal_id}`);
        const trade = event.trade;
        if (!Number.isInteger(trade.quantity) || trade.quantity <= 0) fail(`Invalid quantity in ${event.event_id}`);
        const plannedKey = `${trade.side}:${trade.symbol}`;
        const remainingPlanned = proposal.remaining.get(plannedKey);
        if (remainingPlanned === undefined || trade.quantity > remainingPlanned) fail(`Execution is not covered by proposal ${event.proposal_id}`);
        if (trade.side === "Buy" && (!trade.research_run_path || trade.research_stance !== "Investable Now")) fail(`Buy lacks qualifying research in ${event.event_id}`);
        let position = positions.get(trade.symbol);
        if (!position) {
          position = createPosition(trade);
          positions.set(trade.symbol, position);
        }
        const consideration = trade.quantity * trade.price;
        const costs = trade.fees + trade.slippage;
        if (trade.side === "Buy") {
          const cashRequired = consideration + costs;
          if (cashRequired > cash + 1e-8) fail(`Buy creates negative cash in ${event.event_id}`);
          cash -= cashRequired;
          position.lots.push({quantity: trade.quantity, cost: cashRequired, acquired_at: event.effective_at, event_id: event.event_id});
          position.legal_name = trade.legal_name;
          position.sector = trade.sector ?? position.sector;
          position.market_cap_bucket = trade.market_cap_bucket ?? position.market_cap_bucket;
          position.classification_vintage = trade.classification_vintage ?? position.classification_vintage;
          position.research_run_path = trade.research_run_path ?? position.research_run_path;
          transactions.push({event_id: event.event_id, date: event.effective_at, type: "Buy", symbol: trade.symbol, quantity: trade.quantity, price: trade.price, gross: consideration, costs, net_cash: -cashRequired, proposal_id: event.proposal_id, source_ids: event.source_ids ?? []});
        } else {
          const netProceeds = consideration - costs;
          consumeFifo(position, trade.quantity, netProceeds);
          cash += netProceeds;
          transactions.push({event_id: event.event_id, date: event.effective_at, type: "Sell", symbol: trade.symbol, quantity: trade.quantity, price: trade.price, gross: consideration, costs, net_cash: netProceeds, proposal_id: event.proposal_id, source_ids: event.source_ids ?? []});
        }
        proposal.remaining.set(plannedKey, remainingPlanned - trade.quantity);
        break;
      }
      case "dividend":
        cash += event.amount;
        transactions.push({event_id: event.event_id, date: event.effective_at, type: "Dividend", symbol: event.symbol, quantity: null, price: null, gross: event.amount, costs: 0, net_cash: event.amount, proposal_id: null, source_ids: event.source_ids ?? []});
        break;
      case "corporate_action": { 
        const position = positions.get(event.symbol);
        if (!position) fail(`Corporate action has no holding for ${event.symbol}`);
        if (Math.abs(positionShares(position) - event.shares_before) > 1e-8 || Math.abs(positionCost(position) - event.cost_before) > 0.01) fail(`Corporate action before-state mismatch for ${event.symbol}`);
        const quantityFactor = event.shares_before === 0 ? 0 : event.shares_after / event.shares_before;
        const costFactor = event.cost_before === 0 ? 0 : event.cost_after / event.cost_before;
        for (const lot of position.lots) {
          lot.quantity *= quantityFactor;
          lot.cost *= costFactor;
          if (!Number.isInteger(lot.quantity)) fail(`Corporate action creates fractional shares for ${event.symbol}`);
        }
        transactions.push({event_id: event.event_id, date: event.effective_at, type: event.action_type, symbol: event.symbol, quantity: event.shares_after - event.shares_before, price: null, gross: 0, costs: 0, net_cash: 0, proposal_id: null, source_ids: event.source_ids ?? []});
        break;
      }
      case "price_snapshot":
        for (const observation of event.observations) prices.set(observation.instrument, observation);
        break;
      case "benchmark_snapshot":
        benchmarkObservations.push(...event.observations);
        break;
      case "thesis_snapshot":
      case "thesis_validation": {
        theses.set(event.symbol, {
          symbol: event.symbol,
          thesis: event.thesis,
          invalidation_triggers: event.invalidation_triggers,
          status: event.thesis_status,
          validation_date: event.effective_at,
          controlling_change: event.controlling_change ?? "",
          next_review_condition: event.next_review_condition ?? "",
          research_run_path: event.research_run_path,
        });
        const position = positions.get(event.symbol);
        if (position) {
          position.thesis_status = event.thesis_status;
          position.thesis_date = event.effective_at;
          position.research_run_path = event.research_run_path;
        }
        break;
      }
      case "policy_amendment":
        if (event.new_policy_version !== policy.policy_version && event.new_policy_version > policy.policy_version) fail(`Ledger policy version exceeds current policy in ${event.event_id}`);
        break;
      default:
        fail(`Unsupported event type ${event.event_type}`);
    }

    if (["cash_flow", "trade_execution", "dividend", "corporate_action", "price_snapshot", "benchmark_snapshot"].includes(event.event_type)) {
      const portfolioValue = totalValue();
      const nav = units > 0 ? portfolioValue / units : null;
      const primary = benchmarkObservations.filter((x) => x.instrument === policy.benchmarks.primary).sort((a, b) => a.as_of.localeCompare(b.as_of));
      const benchmarkValue = primary.at(-1)?.value ?? null;
      const benchmarkBase = primary[0]?.value ?? null;
      performance.push({
        date: event.effective_at,
        event_id: event.event_id,
        external_flow: event.event_type === "cash_flow" ? (event.flow_type === "Contribution" ? event.amount : -event.amount) : 0,
        portfolio_value: round(portfolioValue, 2),
        units: round(units, 8),
        nav: round(nav, 8),
        twr: nav === null ? null : round(nav / initialNav - 1),
        benchmark_value: benchmarkValue,
        benchmark_return: benchmarkValue === null || benchmarkBase === null ? null : round(benchmarkValue / benchmarkBase - 1),
      });
    }
  }

  const holdings = [];
  const portfolioValue = totalValue();
  for (const position of [...positions.values()].sort((a, b) => a.symbol.localeCompare(b.symbol))) {
    const shares = positionShares(position);
    if (shares === 0) continue;
    const openCost = positionCost(position);
    const price = prices.get(position.symbol) ?? null;
    const marketValue = price ? shares * price.value : null;
    const unrealized = marketValue === null ? null : marketValue - openCost;
    holdings.push({
      symbol: position.symbol,
      legal_name: position.legal_name,
      sector: position.sector,
      market_cap_bucket: position.market_cap_bucket,
      classification_vintage: position.classification_vintage,
      shares,
      open_cost: round(openCost, 2),
      invested_price: shares ? round(openCost / shares, 4) : null,
      current_price: price?.value ?? null,
      price_as_of: price?.as_of ?? null,
      price_source_id: price?.source_id ?? null,
      market_value: round(marketValue, 2),
      absolute_change: marketValue === null ? null : round(marketValue - openCost, 2),
      percentage_change: marketValue === null || openCost === 0 ? null : round(marketValue / openCost - 1),
      realized_pnl: round(position.realized_pnl, 2),
      unrealized_pnl: round(unrealized, 2),
      portfolio_weight: marketValue === null || portfolioValue === 0 ? null : round(marketValue / portfolioValue),
      thesis_status: position.thesis_status,
      thesis_date: position.thesis_date,
      research_run_path: position.research_run_path,
    });
  }

  const groupSummary = (field, categories = null) => {
    const keys = categories ?? [...new Set(holdings.map((x) => x[field] ?? "Unknown"))].sort();
    return keys.map((key) => {
      const value = holdings.filter((x) => (x[field] ?? "Unknown") === key).reduce((sum, x) => sum + (x.market_value ?? 0), 0);
      return {name: key, market_value: round(value, 2), portfolio_weight: portfolioValue ? round(value / portfolioValue) : null, invested_equity_weight: investedMarketValue() ? round(value / investedMarketValue()) : null};
    });
  };

  const marketCapSummary = groupSummary("market_cap_bucket", ["Large", "Mid", "Small", "Unknown"]).map((row) => ({
    ...row,
    target: {Large: policy.allocation_targets.large, Mid: policy.allocation_targets.mid, Small: policy.allocation_targets.small, Unknown: 0}[row.name],
  }));
  const sectorSummary = groupSummary("sector").sort((a, b) => b.market_value - a.market_value);
  const warnings = [];
  for (const holding of holdings) {
    if (holding.portfolio_weight !== null && holding.portfolio_weight > policy.warnings.single_stock_weight) warnings.push({code: "STOCK_CONCENTRATION", severity: "Soft", scope: holding.symbol, message: `${holding.symbol} exceeds the ${(policy.warnings.single_stock_weight * 100).toFixed(1)}% review threshold`});
    if (holding.current_price === null) warnings.push({code: "MISSING_PRICE", severity: "Hard", scope: holding.symbol, message: `${holding.symbol} has no current price`});
    if (holding.thesis_status !== "Intact") warnings.push({code: "THESIS_STATUS", severity: "Soft", scope: holding.symbol, message: `${holding.symbol} thesis is ${holding.thesis_status}`});
  }
  for (const sector of sectorSummary) if (sector.portfolio_weight !== null && sector.portfolio_weight > policy.warnings.sector_weight) warnings.push({code: "SECTOR_CONCENTRATION", severity: "Soft", scope: sector.name, message: `${sector.name} exceeds the ${(policy.warnings.sector_weight * 100).toFixed(1)}% review threshold`});
  const cashWeight = portfolioValue ? cash / portfolioValue : null;
  if (cashWeight !== null && (cashWeight < policy.cash_policy.minimum - 1e-8 || cashWeight > policy.cash_policy.maximum + 1e-8)) warnings.push({code: "CASH_POLICY", severity: "Soft", scope: "Portfolio", message: `Cash weight ${(cashWeight * 100).toFixed(1)}% is outside policy`});

  const realizedPnl = holdings.reduce((sum, x) => sum + x.realized_pnl, 0) + [...positions.values()].filter((position) => positionShares(position) === 0).reduce((sum, position) => sum + position.realized_pnl, 0);
  const unrealizedPnl = holdings.reduce((sum, x) => sum + (x.unrealized_pnl ?? 0), 0);
  const xirrFlows = [...externalFlows, {date: events.at(-1)?.effective_at ?? policy.created_at, amount: portfolioValue}];
  const state = {
    schema_version: "1.0.0",
    portfolio_id: policy.portfolio_id,
    display_name: policy.display_name,
    policy_version: policy.policy_version,
    as_of: events.at(-1)?.effective_at ?? policy.created_at,
    currency: "INR",
    summary: {
      contributions: round(contributions, 2), withdrawals: round(withdrawals, 2), cash: round(cash, 2),
      invested_cost: round(holdings.reduce((sum, x) => sum + x.open_cost, 0), 2),
      market_value: round(investedMarketValue(), 2), portfolio_value: round(portfolioValue, 2),
      realized_pnl: round(realizedPnl, 2), unrealized_pnl: round(unrealizedPnl, 2),
      cash_weight: round(cashWeight), twr: performance.at(-1)?.twr ?? null, xirr: round(xirr(xirrFlows)),
    },
    holdings,
    transactions,
    performance,
    market_cap_summary: marketCapSummary,
    sector_summary: sectorSummary,
    theses: [...theses.values()].sort((a, b) => a.symbol.localeCompare(b.symbol)),
    warnings,
    sources: [...sources.values()].sort((a, b) => a.source_id.localeCompare(b.source_id)),
    checks: [
      {check: "Cash non-negative", status: cash >= -1e-8 ? "OK" : "FAIL", actual: round(cash, 2), expected: ">= 0", difference: null, tolerance: 0, notes: "Hard account invariant"},
      {check: "Holding weights reconcile", status: holdings.every((x) => x.market_value !== null) ? "OK" : "PARTIAL", actual: round(holdings.reduce((sum, x) => sum + (x.portfolio_weight ?? 0), 0) + (cashWeight ?? 0)), expected: "1.0", difference: holdings.every((x) => x.market_value !== null) ? round(holdings.reduce((sum, x) => sum + (x.portfolio_weight ?? 0), 0) + (cashWeight ?? 0) - 1) : null, tolerance: 0.000001, notes: "Partial when a current price is missing"},
      {check: "Approved executions", status: "OK", actual: transactions.filter((x) => ["Buy", "Sell"].includes(x.type)).length, expected: "All linked to approved proposals", difference: null, tolerance: 0, notes: "Enforced during replay"}
    ]
  };

  await fs.mkdir(path.dirname(args.output), {recursive: true});
  await fs.writeFile(args.output, `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

await main();
