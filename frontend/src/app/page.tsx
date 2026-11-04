import ChatWidget from "@/components/ChatWidget";

export default function Home() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "56px 20px 120px" }}>
      <h1 style={{ fontSize: "2rem", lineHeight: 1.2, marginBottom: 8 }}>SharpBuild AI Website Assistant</h1>
      <p style={{ color: "var(--muted)", marginTop: 0 }}>
        A demo of a website-knowledge chatbot built on the public content of{" "}
        <a href="https://sharpbuild.io/" target="_blank" rel="noopener noreferrer">sharpbuild.io</a>.
        Open the chat in the corner and ask something.
      </p>

      <h2>How it works</h2>
      <ol>
        <li>The site is crawled, cleaned and split into small sections.</li>
        <li>Each section is turned into an embedding and stored in PostgreSQL (pgvector).</li>
        <li>Your question is matched against those sections; weak matches are rejected before any AI call.</li>
        <li>A language model writes a short answer using <em>only</em> the matched sections, with source links.</li>
      </ol>

      <h2>Try these</h2>
      <ul>
        <li>An answerable question: <em>&ldquo;Do you build Shopify stores?&rdquo;</em></li>
        <li>Something the site doesn&apos;t publish: <em>&ldquo;How much does a website cost?&rdquo;</em></li>
        <li>Something unrelated: <em>&ldquo;What&apos;s the weather in Paris?&rdquo;</em></li>
      </ul>

      <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
        Answers can be wrong or out of date. For anything important, contact the team directly.
      </p>
      <ChatWidget />
    </main>
  );
}
