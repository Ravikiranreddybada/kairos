// Server-side proxy: browser -> /v1/* (same origin) -> Render API.
// Adds the API key here so the browser never holds it. Streams SSE through unchanged.
export const config = { maxDuration: 60 }; // covers a Render free cold start (~30-60 s)

const HOP = new Set(["host", "connection", "content-length", "x-api-key", "cookie", "authorization"]);

export default {
  async fetch(req: Request): Promise<Response> {
    const base = process.env.KAIROS_API_URL;
    const key = process.env.KAIROS_WEB_API_KEY;
    if (!base || !key) return Response.json({ detail: "proxy not configured" }, { status: 500 });

    const url = new URL(req.url);
    const path = url.searchParams.get("p") ?? "";
    url.searchParams.delete("p");
    const qs = url.searchParams.toString();
    const target = `${base.replace(/\/$/, "")}/v1/${path}${qs ? `?${qs}` : ""}`;

    const headers = new Headers();
    req.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase())) headers.set(k, v); });
    headers.set("X-API-Key", key);

    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: "manual",
    });
    const out = new Headers(upstream.headers);
    out.delete("content-encoding");
    out.delete("content-length");
    return new Response(upstream.body, { status: upstream.status, headers: out });
  },
};
