"use client";

import { useRef, useState } from "react";

type Match = {
  job_id: number;
  company: string;
  title: string;
  location: string;
  url: string;
  mentions_sponsorship: boolean;
  sponsor_name: string;
  seniority: string;
  similarity: number;
  explanation?: string;
};

type Meta = { years: number; levels: string[] | null };

const STRONG = 0.8;
const MODERATE = 0.74;

function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function join() {
    setStatus("busy");
    setMsg("");
    try {
      const res = await fetch("/api/early-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, website: "" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setStatus("done");
    } catch (e) {
      setStatus("error");
      setMsg(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  if (status === "done") {
    return (
      <p className="waitlist-done">
        ✓ You&apos;re on the list — we&apos;ll email you when Pro opens.
      </p>
    );
  }
  return (
    <div className="waitlist">
      <div className="waitlist-row">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          aria-label="Email address for early access"
          onKeyDown={(e) => e.key === "Enter" && join()}
        />
        <button
          type="button"
          className="waitlist-btn"
          onClick={join}
          disabled={status === "busy" || !email.includes("@")}
        >
          {status === "busy" ? "Joining…" : "Join early access"}
        </button>
      </div>
      {status === "error" && <p className="error">{msg}</p>}
    </div>
  );
}

function band(sim: number): { label: string; cls: string } {
  if (sim >= STRONG) return { label: "Strong match", cls: "band-strong" };
  if (sim >= MODERATE) return { label: "Moderate match", cls: "band-moderate" };
  return { label: "Weak match", cls: "band-weak" };
}

async function extractPdfText(file: File): Promise<string> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url
  ).toString();
  const buf = await file.arrayBuffer();
  const doc = await pdfjs.getDocument({ data: buf }).promise;
  let out = "";
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const content = await page.getTextContent();
    out +=
      content.items
        .map((it) => ("str" in it ? (it as { str: string }).str : ""))
        .join(" ") + "\n";
  }
  return out.trim();
}

export default function Home() {
  const [cv, setCv] = useState("");
  const [fileName, setFileName] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [includeAllLevels, setIncludeAllLevels] = useState(false);
  const [statedOnly, setStatedOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const scannerRef = useRef<HTMLElement>(null);

  async function handleFile(file: File) {
    setError("");
    setReading(true);
    try {
      let text = "";
      if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
        text = await extractPdfText(file);
      } else if (file.type.startsWith("text/") || /\.(txt|md)$/i.test(file.name)) {
        text = await file.text();
      } else {
        throw new Error("Upload a PDF or plain-text file, or paste your CV instead.");
      }
      if (text.length < 100) {
        throw new Error(
          "We couldn't read enough text from that file — it may be a scanned image. Paste your CV instead."
        );
      }
      setCv(text);
      setFileName(file.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that file.");
      setFileName("");
    } finally {
      setReading(false);
    }
  }

  async function runMatch() {
    setLoading(true);
    setError("");
    setMatches(null);
    try {
      const res = await fetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cv, includeAllLevels, statedOnly }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setMatches(data.matches);
      setMeta(data.meta ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const strongOrModerate = matches?.filter((m) => m.similarity >= MODERATE) ?? [];
  const poolIsWeak =
    matches !== null && matches.length > 0 && strongOrModerate.length === 0;

  return (
    <main className="wrap">
      <header className="masthead">
        <div className="mast-left">
          <div className="mark">SR</div>
          <span className="wordmark">Sponsor Radar</span>
        </div>
        <nav className="mast-nav">
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <a
            href="#scanner"
            className="nav-cta"
            onClick={(e) => {
              e.preventDefault();
              scannerRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            Scan my CV
          </a>
        </nav>
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
        </p>
      </section>

      <section className="input-card" id="scanner" ref={scannerRef}>
        <label>Your CV</label>

        <div
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) handleFile(f);
          }}
        >
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <button
            type="button"
            className="upload-btn"
            onClick={() => fileInput.current?.click()}
            disabled={reading}
          >
            {reading ? "Reading file…" : "Upload CV (PDF)"}
          </button>
          <p className="drop-hint">
            {fileName
              ? `Loaded: ${fileName} (${cv.length.toLocaleString()} characters)`
              : "or drag a file here"}
          </p>
          <button
            type="button"
            className="paste-toggle"
            onClick={() => setShowPaste(!showPaste)}
          >
            {showPaste ? "Hide text" : "Paste text instead"}
          </button>
        </div>

        {showPaste && (
          <textarea
            value={cv}
            onChange={(e) => {
              setCv(e.target.value);
              setFileName("");
            }}
            placeholder="Paste the full text of your CV here — skills, projects, experience."
            rows={8}
          />
        )}

        <div className="filters">
          <label className="check">
            <input
              type="checkbox"
              checked={statedOnly}
              onChange={(e) => setStatedOnly(e.target.checked)}
            />
            Only jobs that state sponsorship in the posting
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={includeAllLevels}
              onChange={(e) => setIncludeAllLevels(e.target.checked)}
            />
            Include all seniority levels
          </label>
        </div>

        <div className="input-row">
          <span className="hint">
            Nothing is stored. Your CV is read once, matched, and discarded.
          </span>
          <button
            onClick={runMatch}
            disabled={loading || reading || cv.trim().length < 100}
          >
            {loading ? "Scanning the register…" : "Find my matches"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {poolIsWeak && (
        <section className="coverage-note">
          <p className="coverage-head">No strong matches for your background yet</p>
          <p>
            Our coverage is expanding across sectors. The results below are the
            nearest available, but we would rather tell you they are weak than
            pretend otherwise. Check back — jobs refresh every day.
          </p>
        </section>
      )}

      {matches && matches.length > 0 && (
        <section className="results">
          <p className="results-head">
            {matches.length} matches at A-rated licensed sponsors
          </p>
          {meta && meta.levels && (
            <p className="detect-note">
              We read roughly {meta.years} year{meta.years === 1 ? "" : "s"} of
              experience in your CV, so we're showing{" "}
              {meta.levels.join(", ")} roles — jobs that explicitly refuse
              sponsorship are always excluded. Tick "include all seniority
              levels" above if we got that wrong.
            </p>
          )}
          {matches.map((m, i) => {
            const b = band(m.similarity);
            return (
              <a key={m.job_id} className="job" href={m.url} target="_blank" rel="noreferrer">
                <div className="job-rank">{String(i + 1).padStart(2, "0")}</div>
                <div className="job-body">
                  <h2>{m.title}</h2>
                  <p className="job-meta">{m.company} · {m.location || "UK"}</p>
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

      <section className="story">
        <p className="section-label">Why this exists</p>
        <h2 className="section-title">
          Built by a graduate on the visa clock.
        </h2>
        <div className="story-cols">
          <p>
            If you are on a Graduate visa, you know the routine: find a job you
            like, open the Home Office register — a spreadsheet with over
            125,000 rows — and Ctrl+F the company name. Guess whether the
            salary clears the threshold. Apply. Hope. Repeat, for every single
            application, against a deadline that does not move.
          </p>
          <p>
            Sponsor Radar was built by an international graduate in Manchester
            doing exactly that. It does the cross-referencing automatically:
            live jobs, matched to your CV by meaning rather than keywords, at
            employers verified against the register — with honest labels when
            a match is weak, because false hope costs you time you do not have.
          </p>
        </div>
      </section>

      <section className="how" id="how">
        <p className="section-label">How it works</p>
        <div className="steps">
          <div className="step">
            <p className="step-no">1</p>
            <h3>We track the register</h3>
            <p>
              The Home Office list of licensed sponsors is ingested every
              weekday — 125,000+ organisations, cleaned and matched to live
              job postings across tech, healthcare, engineering, finance,
              education and more.
            </p>
          </div>
          <div className="step">
            <p className="step-no">2</p>
            <h3>Your CV is read for meaning</h3>
            <p>
              Your CV is converted to a semantic fingerprint and compared
              against every live role — so a health analytics graduate matches
              health data jobs, not just postings sharing a keyword.
            </p>
          </div>
          <div className="step">
            <p className="step-no">3</p>
            <h3>Every result is stamped</h3>
            <p>
              Each match shows its register entry, its rating, and whether the
              posting itself mentions sponsorship — and we label match strength
              honestly instead of padding the list.
            </p>
          </div>
        </div>
      </section>

      <section className="stats">
        <div className="stat">
          <p className="stat-n">125,000+</p>
          <p className="stat-l">licensed sponsors tracked</p>
        </div>
        <div className="stat">
          <p className="stat-n">Daily</p>
          <p className="stat-l">register &amp; job refresh</p>
        </div>
        <div className="stat">
          <p className="stat-n">8 sectors</p>
          <p className="stat-l">and expanding</p>
        </div>
      </section>

      <section className="pricing" id="pricing">
        <p className="section-label">Pricing</p>
        <div className="plans">
          <div className="plan">
            <h3>Free</h3>
            <p className="plan-price">£0</p>
            <ul>
              <li>CV scans against the full job pool</li>
              <li>Top 15 matches with confidence labels</li>
              <li>Register verification on every result</li>
            </ul>
            <a
              className="plan-btn"
              href="#scanner"
              onClick={(e) => {
                e.preventDefault();
                scannerRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              Scan my CV
            </a>
          </div>
          <div className="plan plan-pro">
            <h3>Pro <span className="plan-badge">Early access</span></h3>
            <p className="plan-price">£7<span>/month</span></p>
            <ul>
              <li>Daily email alerts for new matches</li>
              <li>Full ranked list, not just the top 15</li>
              <li>Salary-threshold checks per role</li>
              <li>Visa-deadline-aware prioritisation</li>
            </ul>
            <WaitlistForm />
            <p className="plan-note">
              Pro is in development — early-access members get it free while
              we build.
            </p>
          </div>
        </div>
      </section>

      <footer className="footer">
        <p>
          Sponsor data: UK Home Office register of licensed sponsors (Workers).
          Sponsor Radar is an independent tool and is not affiliated with the
          Home Office. A sponsor licence does not guarantee sponsorship for any
          specific role — always confirm with the employer.
        </p>
        <p className="footer-meta">
          Built in Manchester ·{" "}
          <a href="https://github.com/adilh333" target="_blank" rel="noreferrer">
            github.com/adilh333
          </a>
        </p>
      </footer>
    </main>
  );
}
