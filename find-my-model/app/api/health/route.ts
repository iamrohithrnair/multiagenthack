import { spawn } from "node:child_process";
import path from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const backendDir = path.join(process.cwd(), "backend");
  const child = spawn("uv", [
    "run",
    "--project",
    backendDir,
    "--python",
    "3.14.5",
    "python",
    "backend/find_my_model.py",
    "--health",
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
      error: Buffer.concat(stderr).toString() || `health exited with ${code}`,
    }, { status: 500 });
  }

  return NextResponse.json(JSON.parse(Buffer.concat(stdout).toString()));
}
