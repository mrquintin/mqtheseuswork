"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("theseus-local");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, organizationSlug }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      setError(data.error || "Login failed");
      return;
    }

    const next = searchParams.get("next") || "/dashboard";
    router.push(next.startsWith("/") ? next : "/dashboard");
    router.refresh();
  }

  return (
    <main
      style={{
        maxWidth: "400px",
        margin: "0 auto",
        padding: "8rem 2rem",
      }}
    >
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "1.5rem",
          letterSpacing: "0.15em",
          color: "var(--gold)",
          textAlign: "center",
          marginBottom: "0.5rem",
        }}
      >
        THESEUS
      </h1>
      <p
        style={{
          textAlign: "center",
          color: "var(--parchment-dim)",
          fontFamily: "'Inter', sans-serif",
          fontSize: "0.75rem",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          marginBottom: "3rem",
        }}
      >
        Founder Portal
      </p>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div>
          <label
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Organization slug
          </label>
          <input
            type="text"
            value={organizationSlug}
            onChange={(e) => setOrganizationSlug(e.target.value)}
            placeholder="theseus-local"
            autoComplete="organization"
            style={{ marginBottom: "0.25rem" }}
          />
          <p style={{ fontSize: "0.65rem", color: "var(--parchment-dim)", marginBottom: "0.75rem" }}>
            Cloud / multi-tenant login: use your org slug (local seed defaults to <code>theseus-local</code>).
          </p>
        </div>

        <div>
          <label
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="founder@theseus.co"
            required
          />
        </div>

        <div>
          <label
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
        </div>

        {error && (
          <p style={{ color: "var(--ember)", fontSize: "0.9rem" }}>{error}</p>
        )}

        <button
          type="submit"
          className="btn-solid btn"
          disabled={loading}
          style={{ marginTop: "0.5rem", width: "100%", opacity: loading ? 0.6 : 1 }}
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </form>

      <p
        style={{
          textAlign: "center",
          marginTop: "2rem",
          fontFamily: "'Inter', sans-serif",
          fontSize: "0.75rem",
          color: "var(--parchment-dim)",
        }}
      >
        Contact an admin for founder credentials
      </p>

      <div style={{ textAlign: "center", marginTop: "2rem" }}>
        <Link
          href="/"
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "0.65rem",
            letterSpacing: "0.1em",
            color: "var(--gold-dim)",
            textDecoration: "none",
          }}
        >
          ← Back
        </Link>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main style={{ padding: "4rem", textAlign: "center" }}>Loading…</main>}>
      <LoginForm />
    </Suspense>
  );
}

