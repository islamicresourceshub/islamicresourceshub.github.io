# Islamic Resources Hub

> **Multilingual Islamic knowledge articles translated into 39 languages from Nerpatham Weekly (Malayalam)**

[![Live Site](https://img.shields.io/badge/Live%20Site-islamicresourceshub.github.io-blue?style=for-the-badge&logo=github)](https://islamicresourceshub.github.io)
[![Articles](https://img.shields.io/badge/Articles-2396%2B-green?style=for-the-badge)](https://islamicresourceshub.github.io/index.json)
[![Languages](https://img.shields.io/badge/Languages-39-orange?style=for-the-badge)](#-supported-languages)
[![RSS Feed](https://img.shields.io/badge/RSS-Feed-red?style=for-the-badge&logo=rss)](https://islamicresourceshub.github.io/rss.xml)

---

## What is Islamic Resources Hub?

**Islamic Resources Hub** is an open, multilingual digital library of Islamic knowledge articles. Every article originates from **Nerpatham Weekly** (നേർപ്പഥം വാരിക), a widely-read Malayalam Islamic magazine published from Kerala, India — and is **automatically translated into 39 world languages** using AI-powered pipelines.

The goal: **make authentic Islamic knowledge accessible to every person on earth, in their own language.**

---

## Why This Project Matters

- **2,396+ articles** across 12 Islamic knowledge categories
- **39 languages** — from Arabic, English, and Hindi to Amharic, Bosnian, Filipino, and Uzbek
- **Every article** is available in both **HTML** (for reading) and **Markdown** (for AI/LLM consumption)
- **Machine-readable catalog** — perfect for search engines, research tools, and AI applications
- **Fully open source** — hosted on GitHub Pages, freely accessible and forkable
- **Automated pipeline** — new issues of Nerpatham Weekly are processed, translated, and published with minimal human intervention

---

## Quick Start

| What you want | Where to go |
|---|---|
| **Read articles in English** | [islamicresourceshub.github.io/en](https://islamicresourceshub.github.io/en/index.html) |
| **Read articles in Arabic** | [islamicresourceshub.github.io/ar](https://islamicresourceshub.github.io/ar/index.html) |
| **Read articles in Malayalam (original)** | [islamicresourceshub.github.io/ml](https://islamicresourceshub.github.io/ml/index.html) |
| **Browse all languages** | [islamicresourceshub.github.io](https://islamicresourceshub.github.io) |
| **Machine-readable JSON catalog** | [islamicresourceshub.github.io/index.json](https://islamicresourceshub.github.io/index.json) |
| **RSS Feed** | [islamicresourceshub.github.io/rss.xml](https://islamicresourceshub.github.io/rss.xml) |
| **Sitemap** | [islamicresourceshub.github.io/sitemap.xml](https://islamicresourceshub.github.io/sitemap.xml) |
| **LLM Instructions** | [islamicresourceshub.github.io/llms.txt](https://islamicresourceshub.github.io/llms.txt) |

---

## Categories

| Category | Description |
|---|---|
| [Quran & Tafsir](https://islamicresourceshub.github.io/en/quran/index.html) | Quranic interpretation and commentary |
| [Hadith & Sunnah](https://islamicresourceshub.github.io/en/hadith/index.html) | Prophetic traditions and their sciences |
| [Aqeedah & Belief](https://islamicresourceshub.github.io/en/aqeedah/index.html) | Islamic creed and theology |
| [Fiqh](https://islamicresourceshub.github.io/en/fiqh/index.html) | Islamic jurisprudence and rulings |
| [Seerah & Biographies](https://islamicresourceshub.github.io/en/seerah/index.html) | Prophetic biography and Muslim lives |
| [Dawah & Spirituality](https://islamicresourceshub.github.io/en/dawah/index.html) | Islamic preaching and spiritual development |
| [Family & Society](https://islamicresourceshub.github.io/en/family/index.html) | Marriage, parenting, and social issues |
| [Health & Medicine](https://islamicresourceshub.github.io/en/health/index.html) | Health and wellness from an Islamic perspective |
| [Youth & Children](https://islamicresourceshub.github.io/en/youth/index.html) | Content for young Muslims |
| [Islamic History](https://islamicresourceshub.github.io/en/history/index.html) | Historical events and civilizations |
| [Opinion & Analysis](https://islamicresourceshub.github.io/en/opinion/index.html) | Contemporary issues and analysis |
| [Stories & Literature](https://islamicresourceshub.github.io/en/story/index.html) | Narratives and literary works |

---

## Supported Languages

All **39 languages** with articles auto-translated from Malayalam originals:

| | | | | |
|---|---|---|---|---|
| Malayalam (ml) | English (en) | Arabic (ar) | Hindi (hi) | Urdu (ur) |
| Bengali (bn) | Tamil (ta) | Indonesian (id) | Turkish (tr) | French (fr) |
| Spanish (es) | Malay (ms) | German (de) | Portuguese (pt) | Russian (ru) |
| Persian (fa) | Pashto (ps) | Swahili (sw) | Hausa (ha) | Filipino (tl) |
| Chinese (zh) | Japanese (ja) | Korean (ko) | Vietnamese (vi) | Thai (th) |
| Italian (it) | Telugu (te) | Kannada (kn) | Marathi (mr) | Gujarati (gu) |
| Punjabi (pa) | Sinhala (si) | Nepali (ne) | Assamese (as) | Odia (or) |
| Somali (so) | Albanian (sq) | Bosnian (bs) | Amharic (am) | Uzbek (uz) |

Browse any language at: `https://islamicresourceshub.github.io/{lang_code}/`

---

## For AI & Developers

This project is designed to be **AI-friendly by default**:

### Machine-Readable Catalog
Every article is indexed in [`/index.json`](https://islamicresourceshub.github.io/index.json) with structured metadata:
- `slug`, `lang`, `category`, `title`, `summary`
- `html_url` for web links
- `md_url` for clean Markdown consumption

### Markdown for LLM Ingestion
Every article has a `.md` file beside the `.html`:
```
/en/aqeedah/become-the-guardian-of-the-sources-20170128-9.html  ← human readable
/en/aqeedah/become-the-guardian-of-the-sources-20170128-9.md    ← LLM friendly
```

### RSS & Sitemaps
- RSS Feed: [`/rss.xml`](https://islamicresourceshub.github.io/rss.xml)
- Sitemap: [`/sitemap.xml`](https://islamicresourceshub.github.io/sitemap.xml)
- LLM instructions: [`/llms.txt`](https://islamicresourceshub.github.io/llms.txt)

### JSON Catalog Stats
```json
{
  "count": 2396,
  "languages": ["ml", "en", "ar", "hi", "ur", "bn", ...],
  "categories": ["quran", "hadith", "aqeedah", "fiqh", "seerah", ...]
}
```

---

## Project Structure

```
islamicresourceshub.github.io/
├── index.html              # Main landing page
├── index.json              # Machine-readable article catalog
├── llms.txt                # LLM usage instructions
├── rss.xml                 # RSS feed
├── sitemap.xml             # XML sitemap
├── robots.txt              # Search engine directives
├── config.yaml             # Pipeline configuration
├── requirements.txt        # Python dependencies
├── style.css               # Site styles
├── assets/                 # Shared assets
├── src/                    # Pipeline source code
├── ml/                     # Malayalam (canonical) articles
├── en/                     # English articles
├── ar/                     # Arabic articles
├── ...                     # 36 more language directories
└── .github/workflows/      # GitHub Actions automation
```

Each language directory contains category subdirectories:
```
en/
├── index.html
├── quran/
├── hadith/
├── aqeedah/
├── fiqh/
├── seerah/
├── dawah/
├── family/
├── health/
├── youth/
├── history/
├── opinion/
└── story/
```

---

## About the Source: Nerpatham Weekly

**Nerpatham Weekly** (നേർപ്പഥം വാരിക) is a longstanding Malayalam-language Islamic magazine published from Kerala, India. It covers a wide range of Islamic topics — from Quranic commentary and hadith sciences to contemporary social issues, family advice, and youth guidance.

**Islamic Resources Hub** bridges the language gap: articles published in Malayalam are automatically processed, extracted, translated using advanced language models, and published across 39 languages — all within an automated CI/CD pipeline.

---

## Contributing

Contributions are welcome! Whether you want to:
- **Fix a translation** — submit a Pull Request with corrections
- **Report an issue** — open a [GitHub Issue](https://github.com/islamicresourceshub/islamicresourceshub.github.io/issues)
- **Suggest a new language** — open an issue with the language code and name
- **Improve the pipeline** — check `src/` for the processing code

### How to Contribute Translations

1. Fork this repository
2. Navigate to the target language directory (e.g., `en/`)
3. Find the article you want to improve
4. Edit the `.md` file alongside the `.html`
5. Submit a Pull Request

---

## License

This project makes Nerpatham Weekly content available in multiple languages for educational and da'wah purposes. All original content rights belong to Nerpatham Weekly and the respective authors.

---

## SEO Keywords

Islamic articles, Quran tafsir, hadith sunnah, Islamic belief, aqeedah, fiqh, seerah, dawah, Islamic family advice, Muslim youth, Islamic history, Nerpatham Weekly, Malayalam Islamic articles, multilingual Islamic content, Islamic knowledge in 39 languages, free Islamic resources, open source Islamic library, Islamic articles online, Muslim articles, Islamic learning, study Islam online

---

<p align="center">
  <strong>islamicresourceshub.github.io</strong><br>
  <em>Making Islamic knowledge accessible to every language on earth.</em>
</p>
