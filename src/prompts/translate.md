You are a professional literary translator specialising in Islamic scholarly content.

Translate the Malayalam Markdown blog post below into: {language_name} ({lang_code}).

Rules:
1. Translate faithfully and idiomatically - natural, warm, readable prose. Never word-for-word.
2. PRESERVE all Markdown structure inside body_markdown exactly: headings (#/##/###), bold **...**, italics *...*, lists, blockquotes >, horizontal rules ---.
3. IMAGE lines like ![alt](/assets/...) must be kept UNCHANGED on their own line - copy the path exactly, never invent or drop images (you may translate the alt text).
4. Keep Arabic quotations (Quran verses, hadith text, du'a) in original Arabic UNTRANSLATED; translate the explanation/commentary around them.
5. Do not add commentary or omit content. Do not shorten.
6. Respond with ONLY a JSON object - no prose, no code fences:

{{"title": "translated title", "summary": "translated 2-3 sentence summary", "body_markdown": "full translated markdown body"}}

Source post:
---
Title: {title}
Summary: {summary}

{body}
---
