"""Shared document search pipeline.

Exposes standalone functions used by both the /eventninja policy slash command
and the real-time chat monitor cog so the retrieval logic lives in one place.
"""
import logging
import db.queries


# ---------------------------------------------------------------------------
# Term extraction and query expansion (ported from EventNinjaGroup statics)
# ---------------------------------------------------------------------------

def extract_query_terms(question: str) -> list[str]:
    """Tokenize *question* into lower-case search terms.

    Keeps tokens of 3+ characters, plus 2-character all-alpha tokens (e.g. "av").
    Returns a deduplicated ordered list.
    """
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in (question or "").lower())
    raw_tokens = [t.strip() for t in cleaned.split() if t.strip()]

    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) >= 3:
            tokens.append(token)
        elif len(token) == 2 and token.isalpha():
            tokens.append(token)

    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def build_search_query(question: str) -> str:
    """Expand *question* terms for known domain abbreviations (AV, alcohol, harassment).

    Returns a space-joined query string suitable for ``plainto_tsquery``.
    """
    tokens = extract_query_terms(question)
    expanded: set[str] = set(tokens)

    if any(t in expanded for t in {"av", "audio", "visual", "sound", "video", "tech"}):
        expanded.update({"av", "audio", "visual", "sound", "video", "tech", "production", "equipment"})

    if any(t in expanded for t in {"drunk", "drink", "drinking", "alcohol", "intoxicated", "intoxication"}):
        expanded.update({"alcohol", "intoxicated", "intoxication", "sobriety", "conduct", "behavior", "safety"})

    if any(t in expanded for t in {"harass", "harassment", "hostile"}):
        expanded.update({"harassment", "conduct", "behavior", "safety"})

    ordered = sorted(expanded)
    return " ".join(ordered) if ordered else question


def extract_relevant_sections(
    text: str,
    terms: list[str],
    section_size: int = 420,
    max_sections: int = 2,
) -> str:
    """Extract up to *max_sections* snippets from *text* near any matching *term*.

    Snippets are separated by ``\\n...\\n``.
    """
    if not text:
        return ""

    compact = str(text).replace("\r", "")
    lowered = compact.lower()

    positions: list[int] = []
    for term in terms:
        t = (term or "").strip().lower()
        if not t:
            continue
        idx = lowered.find(t)
        if idx >= 0:
            positions.append(idx)

    if not positions:
        return compact[:section_size]

    positions.sort()
    chosen: list[int] = []
    for pos in positions:
        if not chosen or abs(pos - chosen[-1]) > (section_size // 2):
            chosen.append(pos)
        if len(chosen) >= max_sections:
            break

    snippets: list[str] = []
    for pos in chosen:
        start = max(0, pos - (section_size // 3))
        end = min(len(compact), start + section_size)
        snippets.append(compact[start:end].strip())

    return "\n...\n".join(s for s in snippets if s)


# ---------------------------------------------------------------------------
# Full document search pipeline
# ---------------------------------------------------------------------------

DEEP_ANALYZE_LIMIT = 40
CONTEXT_LIMIT = 16


async def search_documents(
    question: str,
    category_filter: list[str] | None = None,
    deep_limit: int = DEEP_ANALYZE_LIMIT,
    context_limit: int = CONTEXT_LIMIT,
) -> list[dict]:
    """Run the full two-stage retrieval pipeline against the ``Document`` table.

    Stage 1 – full-table ``ts_rank_cd`` ranking (no LIMIT) with optional
               category filter.
    Stage 2 – load full ``DocumentValue`` for the top *deep_limit* candidates
               and re-rank by term overlap before returning the top *context_limit*.

    Each returned dict has keys:
        ``Id``, ``title``, ``category``, ``version``, ``rank``, ``document_value``.

    Returns an empty list when no documents match.
    """
    clean_question = (question or "").strip()
    search_query = build_search_query(clean_question)
    question_terms = extract_query_terms(clean_question)
    score_terms = question_terms or extract_query_terms(search_query)

    query_candidates = list({clean_question, search_query} - {""})

    # ---- Stage 1: metadata ranking ----------------------------------------
    docs_by_id: dict[int, dict] = {}

    for search_candidate in query_candidates:
        try:
            rows = await db.queries.search_documents_stage1(search_candidate, category_filter)
        except Exception:
            logging.exception("document_search_service: stage-1 lookup failed")
            continue

        for row in rows:
            doc_id = int(row["Id"])
            rank = float(row["rank"] or 0.0)
            current = docs_by_id.get(doc_id)
            if not current or rank > float(current.get("rank") or 0.0):
                docs_by_id[doc_id] = row

    if not docs_by_id:
        # Fallback: ILIKE pattern match
        tokens = score_terms
        like_terms = [f"%{t.strip()}%" for t in tokens if len(t.strip()) >= 2][:16]
        if like_terms:
            try:
                rows = await db.queries.search_documents_fallback(like_terms, category_filter)
                for row in rows:
                    docs_by_id[int(row["Id"])] = row
            except Exception:
                logging.exception("document_search_service: fallback lookup failed")

    if not docs_by_id:
        return []

    # ---- Metadata re-rank, pick deep candidates ---------------------------
    def _meta_rank(row: dict) -> float:
        title = (row.get("title") or "").lower()
        category = (row.get("category") or "").lower()
        base = float(row.get("rank") or 0.0)
        title_hits = sum(1 for t in score_terms if t in title)
        cat_hits = sum(1 for t in score_terms if t in category)
        return (base * 20.0) + (title_hits * 5.0) + (cat_hits * 3.0)

    ranked = sorted(docs_by_id.values(), key=_meta_rank, reverse=True)
    deep_candidates = ranked[:deep_limit]
    deep_ids = [int(r["Id"]) for r in deep_candidates]

    # ---- Stage 2: load full text and re-rank ------------------------------
    try:
        detailed_rows = await db.queries.search_documents_stage2(deep_ids)
    except Exception:
        logging.exception("document_search_service: stage-2 text load failed")
        return []

    detailed_by_id = {int(r["Id"]): r for r in detailed_rows}

    docs_with_text: list[dict] = []
    for meta in deep_candidates:
        doc_id = int(meta["Id"])
        detailed = detailed_by_id.get(doc_id)
        if not detailed:
            continue
        merged = dict(meta)
        merged["document_value"] = detailed.get("document_value") or ""
        docs_with_text.append(merged)

    def _full_rank(row: dict) -> float:
        title = (row.get("title") or "").lower()
        category = (row.get("category") or "").lower()
        text = str(row.get("document_value") or "").lower()
        base = float(row.get("rank") or 0.0)
        overlap = sum(1 for t in score_terms if t in text)
        title_hits = sum(1 for t in score_terms if t in title)
        cat_hits = sum(1 for t in score_terms if t in category)
        return (base * 10.0) + (overlap * 2.0) + (title_hits * 3.0) + (cat_hits * 2.0)

    return sorted(docs_with_text, key=_full_rank, reverse=True)[:context_limit]
