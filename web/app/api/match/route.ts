import { NextRequest, NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL!;
const SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY!;
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY; // optional

type Match = {
  job_id: number;
  company: string;
  title: string;
  location: string;
  url: string;
  mentions_sponsorship: boolean;
  sponsor_name: string;
  similarity: number;
  explanation?: string;
};

async function embedCv(text: string): Promise<number[]> {
  const res = await fetch(`${SUPABASE_URL}/functions/v1/embed-cv`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${SERVICE_KEY}`,
    },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`embed-cv failed: ${res.status}`);
  const { embedding } = await res.json();
  return embedding;
}

async function matchJobs(embedding: number[]): Promise<Match[]> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/match_jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
    },
    body: JSON.stringify({ query_embedding: embedding, match_count: 15 }),
  });
  if (!res.ok) throw new Error(`match_jobs failed: ${res.status}`);
  return res.json();
}

async function explainTop(cv: string, matches: Match[]): Promise<void> {
  if (!ANTHROPIC_KEY || matches.length === 0) return;
  const top = matches.slice(0, 5);
  const jobList = top
    .map((m, i) => `${i + 1}. ${m.title} at ${m.company} (${m.location})`)
    .join("\n");

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 600,
      messages: [{
        role: "user",
        content:
          `A UK graduate's CV (excerpt):\n${cv.slice(0, 3000)}\n\n` +
          `Top matched jobs:\n${jobList}\n\n` +
          `For each job, write one specific sentence on why this CV fits, ` +
          `naming a concrete skill or project from the CV. Respond ONLY with ` +
          `a JSON array of ${top.length} strings, no markdown, no preamble.`,
      }],
    }),
  });
  if (!res.ok) return; // explanations are enhancement, not requirement
  try {
    const data = await res.json();
    const text = data.content?.find((c: { type: string }) => c.type === "text")?.text ?? "";
    const parsed = JSON.parse(text.replace(/```json|```/g, "").trim());
    parsed.forEach((exp: string, i: number) => {
      if (top[i]) top[i].explanation = exp;
    });
  } catch {
    // ignore malformed explanation output
  }
}

export async function POST(req: NextRequest) {
  try {
    const { cv } = await req.json();
    if (!cv || cv.trim().length < 100) {
      return NextResponse.json(
        { error: "Paste at least 100 characters of your CV." },
        { status: 400 },
      );
    }
    const embedding = await embedCv(cv);
    const matches = await matchJobs(embedding);
    await explainTop(cv, matches);
    return NextResponse.json({ matches });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Matching failed — try again in a moment." },
      { status: 500 },
    );
  }
}
