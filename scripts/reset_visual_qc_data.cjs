const { DatabaseSync } = require("node:sqlite");
const { resolve } = require("node:path");

const positionalPath = process.argv.slice(2).find((argument) => !argument.startsWith("--"));
const databasePath = resolve(positionalPath || "data/visual_qc.db");
const apply = process.argv.includes("--apply");
const database = new DatabaseSync(databasePath);

const tables = [
  "agent_graph_runs",
  "hitl_reviews",
  "workflow_runs",
  "decisions",
  "classifications",
  "defects",
  "inspections",
];

const before = Object.fromEntries(
  tables.map((table) => [table, database.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count]),
);

if (!apply) {
  console.log(JSON.stringify({ database: databasePath, mode: "dry-run", rows: before }, null, 2));
  console.log("Run again with --apply to delete these demo records.");
  database.close();
  process.exit(0);
}

database.exec("BEGIN IMMEDIATE");
try {
  for (const table of tables) database.exec(`DELETE FROM ${table}`);
  database.exec("COMMIT");
} catch (error) {
  database.exec("ROLLBACK");
  database.close();
  throw error;
}

const after = Object.fromEntries(
  tables.map((table) => [table, database.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count]),
);
console.log(JSON.stringify({ database: databasePath, mode: "applied", before, after }, null, 2));
database.close();
