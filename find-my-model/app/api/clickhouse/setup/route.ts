import { spawn } from "node:child_process";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CONFIRM = "ENABLE_CLICKHOUSE_QUERY_ENDPOINT";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  if (body?.confirm !== CONFIRM) {
    return NextResponse.json({
      error: `Set confirm to ${CONFIRM} to create or update the hosted ClickHouse query endpoint.`,
    }, { status: 400 });
  }

  const backendDir = path.join(process.cwd(), "backend");
  const child = spawn("uv", [
    "run",
    "--project",
    backendDir,
    "--python",
    "3.14.5",
    "python",
    "backend/find_my_model.py",
    "--setup-clickhouse-storage",
  ], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  const stdout: Buffer[] = [];
  const stderr: Buffer[] = [];
  child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
  child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));

  const code = await new Promise<number | null>((resolve) => child.on("close", resolve));
  if (code) {
    return NextResponse.json({
      error: Buffer.concat(stderr).toString() || `setup exited with ${code}`,
    }, { status: 500 });
  }

  const lines = Buffer.concat(stdout).toString().split("\n").filter(Boolean);
  const jsonLine = lines.findLast((line) => line.trim().startsWith("{"));
  return NextResponse.json(jsonLine ? JSON.parse(jsonLine) : { ok: true });
}
