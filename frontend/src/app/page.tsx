import ChatWidget from "@/components/ChatWidget";
import TryChips from "@/components/TryChips";
import styles from "./page.module.css";

const STEPS = [
  ["Collect", "The site is crawled, cleaned and split into small sections."],
  [
    "Embed",
    "Each section becomes an embedding stored in PostgreSQL with pgvector.",
  ],
  [
    "Match",
    "Your question is matched to those sections. Weak matches are rejected before any AI call.",
  ],
  [
    "Answer",
    "A language model writes a short answer using only the matched sections, with source links.",
  ],
];

export default function Home() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={`${styles.shell} ${styles.headerInner}`}>
          <a
            className={styles.brand}
            href='https://sharpbuild.io/'
            target='_blank'
            rel='noopener noreferrer'
            aria-label='SharpBuild home'
          >
            <svg
              className={styles.brandMark}
              viewBox='0 0 32 32'
              fill='none'
              aria-hidden='true'
            >
              <rect x='3' y='18' width='10' height='10' rx='1.5' fill='#0f172a' />
              <rect x='11' y='10' width='10' height='10' rx='1.5' fill='#635bff' />
              <rect
                x='19'
                y='4'
                width='10'
                height='10'
                rx='1.5'
                fill='#635bff'
                opacity='.55'
              />
              <circle cx='26.5' cy='6.5' r='1.5' fill='#a8e63a' />
            </svg>
            <span>SharpBuild</span>
          </a>
          <nav className={styles.navigation} aria-label='Main navigation'>
            <a href='#how'>How it works</a>
            <a href='#built'>Technology</a>
            <a
              className={styles.visitLink}
              href='https://sharpbuild.io/'
              target='_blank'
              rel='noopener noreferrer'
            >
              Visit SharpBuild
              <svg viewBox='0 0 20 20' fill='none' aria-hidden='true'>
                <path
                  d='M4 10h11m-5-5 5 5-5 5'
                  stroke='currentColor'
                  strokeWidth='1.7'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </a>
          </nav>
        </div>
      </header>

      <section className={`${styles.shell} ${styles.hero}`}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Portfolio demo · AI website assistant</p>
          <h1 className={styles.title}>
            Get clear answers.
            <br />
            <span className={styles.titleAccent}>Build with confidence.</span>
          </h1>
          <p className={styles.lead}>
            Explore SharpBuild with an assistant that answers from what&apos;s
            published on{" "}
            <a
              href='https://sharpbuild.io/'
              target='_blank'
              rel='noopener noreferrer'
            >
              sharpbuild.io
            </a>
            , and says so honestly when it can&apos;t find an answer.
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryLink} href='#try'>
              Explore the assistant
              <svg viewBox='0 0 20 20' fill='none' aria-hidden='true'>
                <path
                  d='M4 10h11m-5-5 5 5-5 5'
                  stroke='currentColor'
                  strokeWidth='1.7'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </a>
            <span className={styles.actionNote}>
              Answers grounded in SharpBuild&apos;s published content
            </span>
          </div>
        </div>

        <aside className={styles.heroArt} aria-label='Explore SharpBuild topics'>
          <div className={styles.artGlow} aria-hidden='true' />
          <div className={styles.previewCard}>
            <div className={styles.previewTop}>
              <div className={styles.previewBrand}>
                <span className={styles.previewIcon} aria-hidden='true'>
                  <svg viewBox='0 0 32 32' fill='none'>
                    <rect x='3' y='18' width='10' height='10' rx='1.5' fill='#fff' />
                    <rect x='11' y='10' width='10' height='10' rx='1.5' fill='#9a94ff' />
                    <rect
                      x='19'
                      y='4'
                      width='10'
                      height='10'
                      rx='1.5'
                      fill='#9a94ff'
                      opacity='.65'
                    />
                    <circle cx='26.5' cy='6.5' r='1.5' fill='#a8e63a' />
                  </svg>
                </span>
                <span>SharpBuild assistant</span>
              </div>
              <span className={styles.livePill}>Ready to help</span>
            </div>
            <h2 className={styles.previewTitle}>Get to know SharpBuild</h2>
            <p className={styles.previewText}>
              Find answers about the things that matter to your next project.
            </p>
            <div className={styles.topicList}>
              {["Services", "Process", "Portfolio"].map((topic, index) => (
                <div className={styles.topic} key={topic}>
                  <span className={styles.topicMark}>0{index + 1}</span>
                  <span>{topic}</span>
                </div>
              ))}
            </div>
          </div>
          <div className={styles.floatingNote}>
            <span className={styles.floatingCheck} aria-hidden='true'>
              ✓
            </span>
            Helpful answers, with sources
          </div>
        </aside>
      </section>

      <section
        id='try'
        className={`${styles.shell} ${styles.questionsSection}`}
        aria-labelledby='questions'
      >
        <div className={styles.sectionHead}>
          <p className={styles.sectionKicker}>Start a conversation</p>
          <h2 id='questions' className={styles.h2}>
            What would you like to know?
          </h2>
          <p className={styles.sectionDescription}>
            Pick a question to open the assistant, or ask anything about
            SharpBuild.
          </p>
        </div>
        <TryChips
          label='Try the assistant'
          questions={[
            "What services do you offer?",
            "Do you build Shopify stores?",
            "How much does a website cost?",
            "What's the weather in Paris?",
          ]}
        />
      </section>

      <section
        id='how'
        className={`${styles.shell} ${styles.section}`}
        aria-labelledby='how-title'
      >
        <div className={styles.sectionHead}>
          <p className={styles.sectionKicker}>How it works</p>
          <h2 id='how-title' className={styles.h2}>
            Useful answers, grounded in real content.
          </h2>
          <p className={styles.sectionDescription}>
            The assistant looks for relevant information on the website before
            responding, and links back to its sources.
          </p>
        </div>
        <div className={styles.grid}>
          {STEPS.map(([title, text], i) => (
            <article key={title} className={styles.card}>
              <span className={styles.num}>{String(i + 1).padStart(2, "0")}</span>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardText}>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section
        id='built'
        className={`${styles.shell} ${styles.section} ${styles.techSection}`}
        aria-labelledby='built-title'
      >
        <div className={styles.sectionHead}>
          <p className={styles.sectionKicker}>Under the hood</p>
          <h2 id='built-title' className={styles.h2}>
            Built with a modern stack.
          </h2>
          <p className={styles.sectionDescription}>
            A focused demo combining retrieval, streaming answers, and a
            responsive chat experience.
          </p>
        </div>
        <ul className={styles.pills} aria-label='Technology used'>
          {[
            "FastAPI",
            "PostgreSQL + pgvector",
            "Gemini API",
            "Next.js",
            "TypeScript",
            "Vercel",
            "Neon",
          ].map(t => (
            <li key={t} className={styles.pill}>
              {t}
            </li>
          ))}
        </ul>
      </section>

      <section
        className={`${styles.shell} ${styles.trustSection}`}
        aria-labelledby='care-title'
      >
        <div>
          <p className={styles.sectionKicker}>Designed to be trustworthy</p>
          <h2 id='care-title' className={styles.h2}>
            Clear answers. No guesswork.
          </h2>
          <p className={styles.sectionDescription}>
            Useful when it knows, upfront when it doesn&apos;t.
          </p>
        </div>
        <ul className={styles.points}>
          <li>
            <strong>Grounded answers</strong>
            Every claim links to the page it came from.
          </li>
          <li>
            <strong>Honest fallbacks</strong>
            Unknown or unpublished details get a clear response and a way to
            reach a person.
          </li>
          <li>
            <strong>Abuse protection</strong>
            Input limits and rate limiting help protect the service.
          </li>
          <li>
            <strong>Privacy-minded</strong>
            The API logs metadata, not question text. Questions are processed
            by Google&apos;s Gemini API.
          </li>
        </ul>
      </section>

      <footer className={`${styles.shell} ${styles.footer}`}>
        <p>
          Demo project built on the public content of sharpbuild.io. Answers can
          be wrong or out of date; for anything important, contact the team
          directly.
        </p>
        <a href='https://sharpbuild.io/contact' target='_blank' rel='noopener noreferrer'>
          Contact SharpBuild
        </a>
      </footer>
      <ChatWidget />
    </main>
  );
}
