import ChatWidget from "@/components/ChatWidget";
import TryChips from "@/components/TryChips";
import styles from "./page.module.css";

const STEPS = [
  ["Collect", "The site is crawled, cleaned and split into small sections."],
  ["Embed", "Each section becomes an embedding stored in PostgreSQL with pgvector."],
  ["Match", "Your question is matched to those sections. Weak matches are rejected before any AI call."],
  ["Answer", "A language model writes a short answer using only the matched sections, with source links."],
];

export default function Home() {
  return (
    <main className={styles.page}>
      <span className={styles.badge}>Portfolio demo</span>
      <h1 className={styles.title}>SharpBuild AI Website Assistant</h1>
      <p className={styles.lead}>
        A chatbot that answers questions using only what is published on{" "}
        <a href="https://sharpbuild.io/" target="_blank" rel="noopener noreferrer">sharpbuild.io</a>, and says so
        honestly when it can&apos;t find an answer.
      </p>

      <TryChips
        label="Try the assistant"
        questions={[
          "What services do you offer?",
          "Do you build Shopify stores?",
          "How much does a website cost?",
          "What's the weather in Paris?",
        ]}
      />

      <section className={styles.section} aria-labelledby="how">
        <h2 id="how" className={styles.h2}>How it works</h2>
        <div className={styles.grid}>
          {STEPS.map(([title, text], i) => (
            <div key={title} className={styles.card}>
              <span className={styles.num}>{i + 1}</span>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardText}>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="built">
        <h2 id="built" className={styles.h2}>Built with</h2>
        <ul className={styles.pills}>
          {["FastAPI", "PostgreSQL + pgvector", "Gemini API", "Next.js", "TypeScript", "Vercel", "Neon"].map((t) => (
            <li key={t} className={styles.pill}>{t}</li>
          ))}
        </ul>
      </section>

      <section className={styles.section} aria-labelledby="care">
        <h2 id="care" className={styles.h2}>Designed to be trustworthy</h2>
        <ul className={styles.points}>
          <li><strong>Grounded answers.</strong> Every claim links to the page it came from.</li>
          <li><strong>Honest fallbacks.</strong> Unknown or unpublished details (like pricing) get a clear &ldquo;not published&rdquo; and a way to reach a person.</li>
          <li><strong>Abuse protection.</strong> Input limits and rate limiting protect the service and its free quota.</li>
          <li><strong>Privacy-minded.</strong> The API logs only metadata, never the text of your question. Questions are processed by Google&apos;s Gemini API.</li>
        </ul>
      </section>

      <p className={styles.small}>
        Demo project built on the public content of sharpbuild.io. Answers can be wrong or out of date; for anything
        important, contact the team directly.
      </p>
      <ChatWidget />
    </main>
  );
}
