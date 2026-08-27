#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function fail(message) { throw new Error(message); }

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) {
    if (!argv[i]?.startsWith("--") || argv[i + 1] === undefined) fail("Use --policy, --state, and --output arguments");
    args[argv[i].slice(2)] = argv[i + 1];
  }
  if (!args.policy || !args.state || !args.output) fail("Missing --policy, --state, or --output");
  return args;
}

const INR = '₹#,##0;[Red](₹#,##0);-';
const INR2 = '₹#,##0.00;[Red](₹#,##0.00);-';
const PERCENT = '0.0%;[Red](0.0%);-';
const DARK = "#17365D";
const TEAL = "#0F766E";
const LIGHT = "#DCE6F1";
const PALE = "#E2F0D9";
const WARN = "#FFF2CC";
const BAD = "#F4CCCC";
const WHITE = "#FFFFFF";
const BLUE = "#0000FF";
const GREEN = "#008000";
const BLACK = "#000000";

function title(sheet, range, text) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[text]];
  sheet.getRange(range).format = {fill: DARK, font: {bold: true, color: WHITE, size: 16}, verticalAlignment: "center"};
}

function section(sheet, range, text) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[text]];
  sheet.getRange(range).format = {fill: DARK, font: {bold: true, color: WHITE}, verticalAlignment: "center"};
}

function header(sheet, range) {
  sheet.getRange(range).format = {fill: TEAL, font: {bold: true, color: WHITE}, wrapText: true, verticalAlignment: "center"};
}

function styleSheet(sheet) {
  sheet.showGridLines = false;
}

function setWidths(sheet, widths) {
  for (const [column, width] of Object.entries(widths)) sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}

function safe(value, fallback = "") { return value ?? fallback; }

async function main() {
  const args = parseArgs(process.argv);
  const policy = JSON.parse(await fs.readFile(args.policy, "utf8"));
  const state = JSON.parse(await fs.readFile(args.state, "utf8"));
  if (policy.portfolio_id !== state.portfolio_id) fail("Policy/state portfolio mismatch");

  const workbook = Workbook.create();
  workbook.comments.setSelf({displayName: "User"});
  const overview = workbook.worksheets.add("Overview");
  const holdings = workbook.worksheets.add("Holdings");
  const transactions = workbook.worksheets.add("Transactions");
  const performance = workbook.worksheets.add("Performance");
  const thesis = workbook.worksheets.add("Thesis Monitor");
  const checks = workbook.worksheets.add("Sources & Checks");
  for (const sheet of [overview, holdings, transactions, performance, thesis, checks]) styleSheet(sheet);

  // Holdings: raw/source-linked inputs plus formula-driven economics.
  title(holdings, "A1:Q2", `${state.display_name} — Current Holdings`);
  holdings.getRange("A3:Q3").merge();
  holdings.getRange("A3:Q3").values = [[`As of ${state.as_of} | INR | Paper portfolio | Formula cells are black; linked inputs are green`]];
  holdings.getRange("A5:Q5").values = [["Symbol", "Company", "Sector", "Cap Bucket", "Shares", "Invested Price", "Open Cost", "Current Price", "Price Date", "Market Value", "Change / Share", "Change %", "Unrealized P&L", "Weight", "Thesis", "Thesis Date", "Research Run"]];
  header(holdings, "A5:Q5");
  const holdingRows = Math.max(state.holdings.length, 1);
  state.holdings.forEach((item, index) => {
    const row = index + 6;
    holdings.getRange(`A${row}:I${row}`).values = [[item.symbol, item.legal_name, safe(item.sector, "Unknown"), item.market_cap_bucket, item.shares, item.invested_price, item.open_cost, item.current_price, item.price_as_of ? new Date(item.price_as_of) : null]];
    holdings.getRange(`O${row}:Q${row}`).values = [[item.thesis_status, item.thesis_date ? new Date(item.thesis_date) : null, safe(item.research_run_path)]];
    holdings.getRange(`J${row}:N${row}`).formulas = [[
      `=IF(OR(E${row}="",H${row}=""),"",E${row}*H${row})`,
      `=IF(OR(F${row}="",H${row}=""),"",H${row}-F${row})`,
      `=IFERROR(H${row}/F${row}-1,"")`,
      `=IF(OR(G${row}="",J${row}=""),"",J${row}-G${row})`,
      `=IFERROR(J${row}/'Overview'!$B$16,"")`
    ]];
    holdings.getRange(`A${row}:I${row}`).format.font = {color: GREEN};
    holdings.getRange(`J${row}:N${row}`).format.font = {color: BLACK};
    holdings.getRange(`O${row}:Q${row}`).format.font = {color: GREEN};
  });
  const holdingsEnd = 5 + holdingRows;
  holdings.getRange(`E6:E${holdingsEnd}`).format.numberFormat = "#,##0";
  holdings.getRange(`F6:H${holdingsEnd}`).format.numberFormat = INR2;
  holdings.getRange(`I6:I${holdingsEnd}`).format.numberFormat = "yyyy-mm-dd";
  holdings.getRange(`J6:K${holdingsEnd}`).format.numberFormat = INR2;
  holdings.getRange(`L6:L${holdingsEnd}`).format.numberFormat = PERCENT;
  holdings.getRange(`M6:M${holdingsEnd}`).format.numberFormat = INR;
  holdings.getRange(`N6:N${holdingsEnd}`).format.numberFormat = PERCENT;
  holdings.getRange(`P6:P${holdingsEnd}`).format.numberFormat = "yyyy-mm-dd";
  holdings.getRange(`L6:N${holdingsEnd}`).conditionalFormats.add("cellIs", {operator: "lessThan", formula: 0, format: {font: {color: "#9C0006"}, fill: "#FFC7CE"}});
  holdings.getRange(`O6:O${holdingsEnd}`).conditionalFormats.add("containsText", {text: "Broken", format: {fill: BAD, font: {bold: true, color: "#9C0006"}}});
  holdings.getRange(`O6:O${holdingsEnd}`).conditionalFormats.add("containsText", {text: "Weakened", format: {fill: WARN}});
  holdings.freezePanes.freezeRows(5);
  setWidths(holdings, {A: 13, B: 28, C: 18, D: 13, E: 10, F: 15, G: 15, H: 15, I: 14, J: 16, K: 15, L: 12, M: 16, N: 11, O: 16, P: 14, Q: 38});

  // Transactions.
  title(transactions, "A1:L2", `${state.display_name} — Accepted Transactions`);
  transactions.getRange("A4:L4").values = [["Event ID", "Effective Date", "Type", "Symbol", "Quantity", "Price", "Gross", "Costs", "Net Cash", "Proposal ID", "Source IDs", "Notes"]];
  header(transactions, "A4:L4");
  state.transactions.forEach((item, index) => {
    const row = index + 5;
    transactions.getRange(`A${row}:L${row}`).values = [[item.event_id, new Date(item.date), item.type, safe(item.symbol), item.quantity, item.price, item.gross, item.costs, item.net_cash, safe(item.proposal_id), (item.source_ids ?? []).join(", "), safe(item.notes)]];
  });
  const txEnd = Math.max(5, state.transactions.length + 4);
  transactions.getRange(`B5:B${txEnd}`).format.numberFormat = "yyyy-mm-dd";
  transactions.getRange(`E5:E${txEnd}`).format.numberFormat = "#,##0";
  transactions.getRange(`F5:I${txEnd}`).format.numberFormat = INR2;
  transactions.getRange(`A5:L${txEnd}`).format.font = {color: GREEN};
  transactions.freezePanes.freezeRows(4);
  setWidths(transactions, {A: 22, B: 14, C: 16, D: 13, E: 11, F: 14, G: 15, H: 13, I: 15, J: 20, K: 18, L: 28});

  // Performance with formula-driven returns and drawdown.
  title(performance, "A1:J2", `${state.display_name} — Performance`);
  performance.getRange("A4:K4").values = [["Date", "Event ID", "External Flow", "Portfolio Value", "Units", "NAV", "Portfolio TWR", "Benchmark TRI", "Benchmark Return", "Relative Return", "Drawdown"]];
  header(performance, "A4:K4");
  const firstBenchmarkIndex = state.performance.findIndex((item) => item.benchmark_value !== null && item.benchmark_value !== undefined);
  const firstBenchmarkRow = firstBenchmarkIndex === -1 ? null : firstBenchmarkIndex + 5;
  state.performance.forEach((item, index) => {
    const row = index + 5;
    performance.getRange(`A${row}:F${row}`).values = [[new Date(item.date), item.event_id, item.external_flow, item.portfolio_value, item.units, item.nav]];
    performance.getRange(`H${row}`).values = [[item.benchmark_value]];
    performance.getRange(`G${row}`).formulas = [[`=IFERROR(F${row}/$F$5-1,"")`]];
    performance.getRange(`I${row}`).formulas = [[firstBenchmarkRow === null ? '=""' : `=IFERROR(H${row}/$H$${firstBenchmarkRow}-1,"")`]];
    performance.getRange(`J${row}`).formulas = [[`=IF(OR(G${row}="",I${row}=""),"",G${row}-I${row})`]];
    performance.getRange(`K${row}`).formulas = [[`=IFERROR(F${row}/MAX($F$5:F${row})-1,"")`]];
    performance.getRange(`A${row}:F${row}`).format.font = {color: GREEN};
    performance.getRange(`H${row}`).format.font = {color: GREEN};
    performance.getRange(`G${row}`).format.font = {color: BLACK};
    performance.getRange(`I${row}:K${row}`).format.font = {color: BLACK};
  });
  const perfEnd = Math.max(5, state.performance.length + 4);
  performance.getRange(`A5:A${perfEnd}`).format.numberFormat = "yyyy-mm-dd";
  performance.getRange(`C5:D${perfEnd}`).format.numberFormat = INR;
  performance.getRange(`E5:F${perfEnd}`).format.numberFormat = "#,##0.0000";
  performance.getRange(`G5:G${perfEnd}`).format.numberFormat = PERCENT;
  performance.getRange(`H5:H${perfEnd}`).format.numberFormat = "#,##0.00";
  performance.getRange(`I5:K${perfEnd}`).format.numberFormat = PERCENT;
  performance.freezePanes.freezeRows(4);
  setWidths(performance, {A: 14, B: 22, C: 16, D: 18, E: 14, F: 14, G: 16, H: 16, I: 17, J: 16, K: 14});

  // Thesis monitor.
  title(thesis, "A1:H2", `${state.display_name} — Thesis Monitor`);
  thesis.getRange("A4:H4").values = [["Symbol", "Status", "Validation Date", "Current Thesis", "Invalidation Triggers", "Controlling Change", "Next Review Condition", "Research Run"]];
  header(thesis, "A4:H4");
  state.theses.forEach((item, index) => {
    const row = index + 5;
    thesis.getRange(`A${row}:H${row}`).values = [[item.symbol, item.status, item.validation_date ? new Date(item.validation_date) : null, item.thesis, (item.invalidation_triggers ?? []).join("; "), safe(item.controlling_change), safe(item.next_review_condition), item.research_run_path]];
  });
  const thesisEnd = Math.max(5, state.theses.length + 4);
  thesis.getRange(`A5:H${thesisEnd}`).format.font = {color: GREEN};
  thesis.getRange(`C5:C${thesisEnd}`).format.numberFormat = "yyyy-mm-dd";
  thesis.getRange(`B5:B${thesisEnd}`).conditionalFormats.add("containsText", {text: "Broken", format: {fill: BAD, font: {bold: true, color: "#9C0006"}}});
  thesis.getRange(`B5:B${thesisEnd}`).conditionalFormats.add("containsText", {text: "Weakened", format: {fill: WARN}});
  thesis.getRange(`D5:G${thesisEnd}`).format.wrapText = true;
  thesis.freezePanes.freezeRows(4);
  setWidths(thesis, {A: 13, B: 16, C: 15, D: 42, E: 42, F: 35, G: 35, H: 38});

  // Sources and checks.
  title(checks, "A1:H2", `${state.display_name} — Sources & Checks`);
  section(checks, "A4:H4", "Model checks");
  checks.getRange("A5:G5").values = [["Check", "Actual", "Expected", "Difference", "Tolerance", "Status", "Notes"]];
  header(checks, "A5:G5");
  state.checks.forEach((item, index) => {
    const row = index + 6;
    checks.getRange(`A${row}:G${row}`).values = [[item.check, item.actual, item.expected, item.difference, item.tolerance, item.status, item.notes]];
  });
  const stateCheckEnd = 5 + state.checks.length;
  const formulaStart = stateCheckEnd + 1;
  checks.getRange(`A${formulaStart}:G${formulaStart + 2}`).values = [
    ["Workbook holding weights", null, 1, null, 0.000001, null, "Holdings plus cash must reconcile to portfolio value"],
    ["Workbook portfolio value", null, state.summary.portfolio_value, null, 0.01, null, "Holdings market value plus cash"],
    ["Workbook formula errors", 0, 0, 0, 0, "OK", "Final error scan is also required before export"]
  ];
  checks.getRange(`B${formulaStart}`).formulas = [[`=IFERROR(SUM('Holdings'!N6:N205)+'Overview'!B14,0)`]];
  checks.getRange(`D${formulaStart}`).formulas = [[`=B${formulaStart}-C${formulaStart}`]];
  checks.getRange(`F${formulaStart}`).formulas = [[`=IF(ABS(D${formulaStart})<=E${formulaStart},"OK","FAIL")`]];
  checks.getRange(`B${formulaStart + 1}`).formulas = [[`=SUM('Holdings'!J6:J205)+'Overview'!B13`]];
  checks.getRange(`D${formulaStart + 1}`).formulas = [[`=B${formulaStart + 1}-C${formulaStart + 1}`]];
  checks.getRange(`F${formulaStart + 1}`).formulas = [[`=IF(ABS(D${formulaStart + 1})<=E${formulaStart + 1},"OK","FAIL")`]];
  checks.getRange(`B${formulaStart}:F${formulaStart + 1}`).format.font = {color: BLACK};
  checks.getRange(`B6:E${formulaStart + 2}`).format.numberFormat = "0.0000";
  checks.getRange(`F6:F${formulaStart + 2}`).conditionalFormats.add("containsText", {text: "OK", format: {fill: PALE, font: {bold: true, color: "#006100"}}});
  checks.getRange(`F6:F${formulaStart + 2}`).conditionalFormats.add("containsText", {text: "FAIL", format: {fill: BAD, font: {bold: true, color: "#9C0006"}}});
  const sourceStart = formulaStart + 5;
  section(checks, `A${sourceStart}:H${sourceStart}`, "Input sources");
  checks.getRange(`A${sourceStart + 1}:G${sourceStart + 1}`).values = [["Source ID", "Title", "Publisher", "Data Date", "Accessed At", "URL", "Notes"]];
  header(checks, `A${sourceStart + 1}:G${sourceStart + 1}`);
  state.sources.forEach((item, index) => {
    const row = sourceStart + 2 + index;
    checks.getRange(`A${row}:G${row}`).values = [[item.source_id, item.title, item.publisher, new Date(item.data_date), new Date(item.accessed_at), item.url, safe(item.notes)]];
  });
  const sourceEnd = Math.max(sourceStart + 2, sourceStart + 1 + state.sources.length);
  checks.getRange(`A${sourceStart + 2}:G${sourceEnd}`).format.font = {color: GREEN};
  checks.getRange(`D${sourceStart + 2}:E${sourceEnd}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  checks.getRange(`F${sourceStart + 2}:G${sourceEnd}`).format.wrapText = true;
  checks.freezePanes.freezeRows(5);
  setWidths(checks, {A: 30, B: 20, C: 20, D: 16, E: 16, F: 46, G: 40, H: 4});

  // Overview is created last so its formulas can link to completed sheets.
  title(overview, "A1:H2", `${state.display_name} — Portfolio Overview`);
  overview.getRange("A3:H3").merge();
  overview.getRange("A3:H3").values = [[`${policy.strategy.label}: ${policy.strategy.explanation}`]];
  overview.getRange("A3:H3").format = {fill: LIGHT, font: {italic: true, color: DARK}, wrapText: true};
  overview.getRange("A5:B5").values = [["Policy", "Value"]];
  header(overview, "A5:B5");
  overview.getRange("A6:B10").values = [
    ["As of", new Date(state.as_of)],
    ["Rolling horizon", `${policy.horizon.years} years`],
    ["Market-cap target", `${(policy.allocation_targets.large * 100).toFixed(0)}% large / ${(policy.allocation_targets.mid * 100).toFixed(0)}% mid / ${(policy.allocation_targets.small * 100).toFixed(0)}% small`],
    ["Tactical cash", `${(policy.cash_policy.minimum * 100).toFixed(0)}%–${(policy.cash_policy.maximum * 100).toFixed(0)}%`],
    ["Soft warnings", `${(policy.warnings.single_stock_weight * 100).toFixed(0)}% stock / ${(policy.warnings.sector_weight * 100).toFixed(0)}% sector`]
  ];
  overview.getRange("B6:B10").format.font = {color: BLUE};
  overview.getRange("B6").format.numberFormat = "yyyy-mm-dd";
  section(overview, "A12:B12", "Portfolio KPIs");
  overview.getRange("A13:A21").values = [["Cash"], ["Cash Weight"], ["Holdings Value"], ["Portfolio Value"], ["Invested Cost"], ["Realized P&L"], ["Unrealized P&L"], ["TWR"], ["XIRR"]];
  overview.getRange("B13").values = [[state.summary.cash]];
  overview.getRange("B14").formulas = [[`=IFERROR(B13/B16,"")`]];
  overview.getRange("B15").formulas = [[`=SUM('Holdings'!J6:J205)`]];
  overview.getRange("B16").formulas = [["=B13+B15"]];
  overview.getRange("B17").values = [[state.summary.invested_cost]];
  overview.getRange("B18").values = [[state.summary.realized_pnl]];
  overview.getRange("B19").formulas = [[`=SUM('Holdings'!M6:M205)`]];
  overview.getRange("B20").values = [[state.summary.twr]];
  overview.getRange("B21").values = [[state.summary.xirr]];
  overview.getRange("B13:B21").format.numberFormat = INR;
  overview.getRange("B14").format.numberFormat = PERCENT;
  overview.getRange("B20:B21").format.numberFormat = PERCENT;
  overview.getRange("B13:B21").format.font = {color: GREEN};
  overview.getRange("B14:B16").format.font = {color: BLACK};
  overview.getRange("B19").format.font = {color: BLACK};
  section(overview, "D5:F5", "Market-cap allocation (invested equity)");
  overview.getRange("D6:F6").values = [["Bucket", "Target", "Actual"]];
  header(overview, "D6:F6");
  ["Large", "Mid", "Small", "Unknown"].forEach((bucket, index) => {
    const row = index + 7;
    const target = {Large: policy.allocation_targets.large, Mid: policy.allocation_targets.mid, Small: policy.allocation_targets.small, Unknown: 0}[bucket];
    overview.getRange(`D${row}:E${row}`).values = [[bucket, target]];
    overview.getRange(`F${row}`).formulas = [[`=IFERROR(SUMIF('Holdings'!D$6:D$205,D${row},'Holdings'!J$6:J$205)/SUM('Holdings'!J$6:J$205),"")`]];
  });
  overview.getRange("E7:F10").format.numberFormat = PERCENT;
  overview.getRange("E7:E10").format.font = {color: BLUE};
  overview.getRange("F7:F10").format.font = {color: BLACK};
  section(overview, "D12:F12", "Sector exposure");
  overview.getRange("D13:F13").values = [["Sector", "Market Value", "Portfolio Weight"]];
  header(overview, "D13:F13");
  state.sector_summary.slice(0, 10).forEach((item, index) => {
    const row = index + 14;
    overview.getRange(`D${row}`).values = [[item.name]];
    overview.getRange(`E${row}`).formulas = [[`=SUMIF('Holdings'!C$6:C$205,D${row},'Holdings'!J$6:J$205)`]];
    overview.getRange(`F${row}`).formulas = [[`=IFERROR(E${row}/$B$16,"")`]];
  });
  const sectorEnd = Math.max(14, 13 + Math.min(10, state.sector_summary.length));
  overview.getRange(`E14:E${sectorEnd}`).format.numberFormat = INR;
  overview.getRange(`F14:F${sectorEnd}`).format.numberFormat = PERCENT;
  overview.getRange(`E14:F${sectorEnd}`).format.font = {color: BLACK};
  section(overview, "A24:B24", "Current warnings");
  overview.getRange("A25:B25").values = [["Severity / Scope", "Message"]];
  header(overview, "A25:B25");
  state.warnings.slice(0, 15).forEach((warning, index) => overview.getRange(`A${index + 26}:B${index + 26}`).values = [[`${warning.severity} — ${warning.scope}`, warning.message]]);
  const warningEnd = Math.max(26, 25 + Math.min(15, state.warnings.length));
  overview.getRange(`A26:B${warningEnd}`).format.wrapText = true;
  overview.getRange(`A26:B${warningEnd}`).conditionalFormats.add("containsText", {text: "Hard", format: {fill: BAD}});
  overview.getRange(`A26:B${warningEnd}`).conditionalFormats.add("containsText", {text: "Soft", format: {fill: WARN}});
  overview.freezePanes.freezeRows(3);
  setWidths(overview, {A: 24, B: 40, C: 4, D: 22, E: 18, F: 18, G: 4, H: 4});

  const capChart = overview.charts.add("bar", overview.getRange("D6:F10"));
  capChart.title = "Market-cap allocation: target vs actual";
  capChart.hasLegend = true;
  capChart.yAxis = {numberFormatCode: "0%"};
  capChart.setPosition("H5", "N18");
  if (state.sector_summary.length > 0) {
    const sectorChart = overview.charts.add("bar", overview.getRange(`D13:E${sectorEnd}`));
    sectorChart.title = "Sector exposure (₹)";
    sectorChart.hasLegend = false;
    sectorChart.xAxis = {numberFormatCode: "₹#,##0"};
    sectorChart.setPosition("H20", "N36");
  }
  if (state.performance.length >= 2) {
    const perfChart = performance.charts.add("line", {chartType: "line", title: "Portfolio and benchmark return", hasLegend: true});
    perfChart.title = "Portfolio and benchmark return";
    perfChart.hasLegend = true;
    const portfolioSeries = perfChart.series.add("Portfolio TWR");
    portfolioSeries.categoryFormula = `'Performance'!$A$5:$A$${perfEnd}`;
    portfolioSeries.formula = `'Performance'!$G$5:$G$${perfEnd}`;
    const benchmarkSeries = perfChart.series.add("Benchmark Return");
    benchmarkSeries.categoryFormula = `'Performance'!$A$5:$A$${perfEnd}`;
    benchmarkSeries.formula = `'Performance'!$I$5:$I$${perfEnd}`;
    perfChart.yAxis = {numberFormatCode: "0.0%"};
    perfChart.setPosition("L4", "S20");
  }

  // Compact programmatic verification before export.
  const keyRange = await workbook.inspect({kind: "table", sheetId: "Overview", range: "A1:F30", include: "values,formulas", tableMaxRows: 30, tableMaxCols: 8, maxChars: 8000});
  if (!keyRange.ndjson) fail("Overview inspection returned no data");
  const errors = await workbook.inspect({kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: {useRegex: true, maxResults: 300}, summary: "final formula error scan"});
  if (errors.ndjson && /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/.test(errors.ndjson)) fail(`Workbook formula error scan failed: ${errors.ndjson}`);

  const previewDir = await fs.mkdtemp(path.join(path.dirname(args.output), ".portfolio-preview-"));
  try {
    for (const sheetName of ["Overview", "Holdings", "Transactions", "Performance", "Thesis Monitor", "Sources & Checks"]) {
      const preview = await workbook.render({sheetName, autoCrop: "all", scale: 1, format: "png"});
      await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "-")}.png`), new Uint8Array(await preview.arrayBuffer()));
    }
    await fs.mkdir(path.dirname(args.output), {recursive: true});
    const output = await SpreadsheetFile.exportXlsx(workbook);
    await output.save(args.output);
  } finally {
    await fs.rm(previewDir, {recursive: true, force: true});
  }
}

await main();
