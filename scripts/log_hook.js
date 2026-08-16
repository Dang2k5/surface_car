#!/usr/bin/env node
/**
 * Windows-friendly Codex hook logger.
 * Reads UTF-8 JSON from stdin and appends normalized entries to ai-log JSONL.
 */
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

function git(...args) {
  try {
    return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function getTool() {
  const arg = process.argv.find((value) => value.startsWith("--tool="));
  return (arg ? arg.slice("--tool=".length) : process.env.AI_TOOL_NAME || "codex").toLowerCase();
}

function vietnamTimestamp() {
  const vietnamOffsetMs = 7 * 60 * 60 * 1000;
  return new Date(Date.now() + vietnamOffsetMs).toISOString().replace("Z", "+07:00");
}

function main() {
  const raw = fs.readFileSync(0, "utf8").trim();
  if (!raw) return null;

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }

  const event = String(data.hook_event_name || data.event || "");

  const origin = git("remote", "get-url", "origin");
  if (!origin) return event;

  const prompt = String(data.prompt || "");
  const lifecycleEvents = new Set(["Stop", "stop", "SessionEnd", "sessionEnd", "AfterModel"]);
  if (!prompt && !lifecycleEvents.has(event)) return event;

  const repo = origin.replace(/\/+$/, "").split("/").pop().replace(/\.git$/, "");
  const entry = {
    ts: vietnamTimestamp(),
    tool: getTool(),
    event,
    session_id: String(data.session_id || data.conversation_id || data.generation_id || ""),
    model: String(data.model || ""),
    repo,
    branch: git("rev-parse", "--abbrev-ref", "HEAD"),
    commit: git("rev-parse", "--short", "HEAD"),
    student: git("config", "user.email"),
    prompt: prompt.slice(0, 1000),
    turn_id: String(data.turn_id || ""),
    transcript_path: String(data.transcript_path || ""),
  };

  const logDir = process.env.AI_LOG_DIR || ".ai-log";
  fs.mkdirSync(logDir, { recursive: true });
  fs.appendFileSync(path.join(logDir, "session.jsonl"), `${JSON.stringify(entry)}\n`, "utf8");
  return event;
}

// Logging must never interrupt Codex, even if the workspace is incomplete.
try {
  const event = main();
  // UserPromptSubmit treats empty stdout as a successful no-op. Stop, however,
  // requires a valid JSON result whenever the hook exits successfully.
  if (event === "Stop") process.stdout.write('{"continue":true}\n');
} catch {
  // Do not let a logging error create a second, invalid Stop-hook result.
  process.stdout.write('{"continue":true}\n');
  process.exitCode = 0;
}
