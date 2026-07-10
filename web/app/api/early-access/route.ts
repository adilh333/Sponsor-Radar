import { NextRequest, NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL!;
const SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY!;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export async function POST(req: NextRequest) {
  try {
    const { email, website } = await req.json();

    // Honeypot: real users never fill the hidden "website" field.
    if (website) return NextResponse.json({ ok: true });

    const clean = (email || "").trim().toLowerCase();
    if (!EMAIL_RE.test(clean) || clean.length > 254) {
      return NextResponse.json(
        { error: "Enter a valid email address." },
        { status: 400 },
      );
    }

    const res = await fetch(`${SUPABASE_URL}/rest/v1/early_access`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        Prefer: "resolution=ignore-duplicates",
      },
      body: JSON.stringify({ email: clean }),
    });

    if (!res.ok && res.status !== 409) {
      throw new Error(`insert failed: ${res.status}`);
    }
    // Duplicates return success too — "you're on the list" is true either way.
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Something went wrong — try again in a moment." },
      { status: 500 },
    );
  }
}
