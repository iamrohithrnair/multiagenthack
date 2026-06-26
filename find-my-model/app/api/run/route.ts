import { spawn } from "node:child_process";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

import type { RunRequest } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as RunRequest;
  const encoder = new TextEncoder();
  const backendDir = path.join(process.cwd(), "backend");

  const stream = new ReadableStream({
    start(controller) {
      const child = spawn("uv", [
        "run",
        "--project",
        backendDir,
        "--python",
        "3.14.5",
        "python",
        "backend/find_my_model.py",
      ], {
        cwd: process.cwd(),
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });

      child.stdin.end(JSON.stringify(body));

      child.stdout.on("data", (chunk: Buffer) => {
        controller.enqueue(encoder.encode(chunk.toString()));
      });

      child.stderr.on("data", (chunk: Buffer) => {
        controller.enqueue(encoder.encode(JSON.stringify({
          type: "error",
          data: chunk.toString().trim(),
          timestamp: Date.now(),
        }) + "\n"));
      });

      child.on("close", (code) => {
        if (code && code !== 0) {
          controller.enqueue(encoder.encode(JSON.stringify({
            type: "error",
            data: `Python backend exited with ${code}`,
            timestamp: Date.now(),
          }) + "\n"));
        }
        controller.close();
      });
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
