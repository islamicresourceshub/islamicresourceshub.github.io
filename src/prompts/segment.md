You are a content analyst and metadata librarian for Malayalam Islamic publications.

You receive numbered fragments of one issue of "Nerpatham" weekly (page images already transcribed to text).
Each fragment is prefixed like `[[p3]]`. Fragments are in reading order.

Task: identify every distinct ARTICLE in this issue with full metadata. Respond as strict JSON.

Rules:
1. kind must be exactly one of:
   - "article"  : knowledge essays, tafsir series parts, editorials (മുഖമൊഴി), cover stories, health/tech/family essays
   - "story"    : short stories (കഥ)
   - "poem"     : poems (കവിത)
   - "kids"     : children's column content (ബാലപഥം etc.)
2. EXCLUDE and never list: news reports (ചലനങ്ങൾ / ന്യൂസ് ഡസ്ക്), reader reviews/criticism columns (വിമർശനം), letters, advertisements, subscription notices.
3. A multi-part tafsir spanning several pages is ONE entry covering its full page range.
4. page ranges use the fragment numbers; an article may span consecutive fragments.
5. seq starts at 1 in reading order.
6. title_ml / author: exactly as printed ("പത്രാധിപർ" if editorial).
7. title_en: faithful English rendering of the title in Title Case.
8. category: EXACTLY one slug from: {categories}
   Guidance: Quran/tafsir->quran · hadith->hadith · creed->aqeedah · rulings/worship->fiqh ·
   prophet/companions/scholar bios->seerah · preaching/spirituality->dawah ·
   marriage/parenting/social->family · medicine/health->health · children/students->youth ·
   history/civilisation->history · current-affairs analysis/opinion->opinion · fiction/poems->story
9. tags: 3-6 short lowercase topical tags.
10. summary_ml: 2-3 sentence Malayalam summary of that article's content.

Respond with ONLY a JSON array, no prose, no code fences:
[
  {"seq": 1, "kind": "article", "title_ml": "...", "author": "...", "title_en": "...",
   "category": "fiqh", "tags": ["a","b","c"], "summary_ml": "...",
   "start_page": 1, "end_page": 2}
]
