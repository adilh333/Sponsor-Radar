// Sponsor Radar — Edge Function: embed CV text with Supabase's built-in
// gte-small model. Same model as embed_jobs.py, so vectors are comparable.
//
// Deploy:  supabase functions deploy embed-cv --no-verify-jwt
// (or paste into the Edge Functions editor in the Supabase dashboard)

const session = new Supabase.ai.Session("gte-small");

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("POST only", { status: 405 });
  }
  const { text } = await req.json();
  if (!text || typeof text !== "string" || text.length < 100) {
    return new Response(
      JSON.stringify({ error: "Provide at least 100 characters of CV text" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  const embedding = await session.run(text.slice(0, 8000), {
    mean_pool: true,
    normalize: true,
  });

  return new Response(JSON.stringify({ embedding }), {
    headers: { "Content-Type": "application/json" },
  });
});
