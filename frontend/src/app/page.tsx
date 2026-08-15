export default function Home() {
  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>CV Analyzer</h1>
      <p>Backend health check: <a href="http://localhost:8000/health">/health</a></p>
    </main>
  );
}
