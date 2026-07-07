"use client";

import { useState } from "react";

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

// Bands calibrated for gte-small cosine similarity. Adjust after observing
// real CVs: a strongly relevant CV should land its top matches in "strong".
const STRONG = 0.8;
const MODERATE = 0.74;

function band(sim: number): { label: string; cls: string } {
  if (sim >= STRONG) return { label: "Strong match", cls: "band-strong" };
  if (sim >= MODERATE) return { label: "Moderate match", cls: "band-moderate" };
  return { label: "Weak match", cls: "band-weak" };
}

export default function Home() {
  const [cv, setCv] = useState("");
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runMatch() {
    setLoading(true);
    setError("");
    setMatches(null);
    try {
      const res = await fetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cv }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setMatches(data.matches);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const strongOrModerate =
    matches?.filter((m) => m.similarity >= MODERATE) ?? [];
  const poolIsWeak = matches !== null && matches.length > 0 && strongOrModerate.length === 0;

  return (
    <main className="wrap">
      <header className="masthead">
        <div className="mark">SR</div>
        <span className="wordmark">Sponsor Radar</span>
      </header>

      <section className="hero">
        <p className="eyebrow">For graduates who need visa sponsorship</p>
        <h1>
          Every job below can<br />actually sponsor you.
        </h1>
        <p className="lede">
          We cross-reference live UK job postings against the Home Office
          register of licensed sponsors — updated daily — so you stop
          researching companies that were never going to sponsor anyone.
          Paste your CV to see your matches.
        </p>
      </section>

      <section className="input-card">
        <label htmlFor="cv">Your CV</label>
        <textarea
          id="cv"
          value={cv}
          onChange={(e) => setCv(e.target.value)}
          placeholder="Paste the full text of your CV here — skills, projects, experience. The more detail, the better the matches."
          rows={10}
        />
        <div className="input-row">
          <span className="hint">
            Nothing is stored. Your CV is used once to find matches.
          </span>
          <button onClick={runMatch} disabled={loading || cv.trim().length < 100}>
            {loading ? "Scanning the register…" : "Find my matches"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {poolIsWeak && (
        <section className="coverage-note">
          <p className="coverage-head">No strong matches for your background yet</p>
          <p>
            Our job coverage is currently strongest in technology, fintech and
            data roles. The results below are the nearest available, but we
            would rather tell you they are weak than pretend otherwise.
            Coverage of healthcare, education and other sectors is being added.
          </p>
        </section>
      )}

      {matches && matches.length > 0 && (
        <section className="results">
          <p className="results-head">
            {matches.length} matches at A-rated licensed sponsors
          </p>
          {matches.map((m, i) => {
            const b = band(m.similarity);
            return (
              <a key={m.job_id} className="job" href={m.url} target="_blank" rel="noreferrer">
                <div className="job-rank">{String(i + 1).padStart(2, "0")}</div>
                <div className="job-body">
                  <h2>{m.title}</h2>
                  <p className="job-meta">
                    {m.company} · {m.location || "UK"}
                  </p>
                  <p className={`job-band ${b.cls}`}>
                    {b.label} · {(m.similarity * 100).toFixed(0)}%
                  </p>
                  {m.explanation && <p className="job-why">{m.explanation}</p>}
                  <p className="job-register">
                    Register entry: {m.sponsor_name} · Skilled Worker, A-rated
                  </p>
                </div>
                <div
                  className={`stamp ${m.mentions_sponsorship ? "stamp-confirmed" : "stamp-likely"}`}
                  aria-label={
                    m.mentions_sponsorship
                      ? "Sponsorship mentioned in the job posting"
                      : "Company holds an A-rated sponsor licence"
                  }
                >
                  {m.mentions_sponsorship ? "Sponsorship stated" : "Licensed sponsor"}
                </div>
              </a>
            );
          })}
          <p className="disclaimer">
            A licence means the company <em>can</em> sponsor — always confirm
            sponsorship for the specific role before relying on it.
          </p>
        </section>
      )}

      {matches && matches.length === 0 && (
        <section className="coverage-note">
          <p className="coverage-head">No live matches right now</p>
          <p>
            Nothing in the current job pool matched your CV. Check back soon —
            jobs refresh daily and new sectors are being added.
          </p>
        </section>
      )}
    </main>
  );
}
