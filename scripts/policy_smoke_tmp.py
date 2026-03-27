import asyncio
from ai.provider import get_provider
from bot.cogs.staffninja import EventNinjaGroup
from db.connection import Database

q = "what would happen if i was drunk on staff"


async def main() -> None:
    group = EventNinjaGroup()
    search_query = group._build_policy_search_query(q)

    docs = await Database.fetch(
        '''
        SELECT "Id", COALESCE("Title", '') AS title, COALESCE("Category", '') AS category,
               COALESCE("Version", '') AS version, COALESCE("DocumentValue", '') AS document_value,
               ts_rank_cd(to_tsvector('english', COALESCE("Title", '') || ' ' || COALESCE("Category", '') || ' ' || COALESCE("DocumentValue", '')),
                          plainto_tsquery('english', $1)) AS rank
        FROM "Document"
        WHERE to_tsvector('english', COALESCE("Title", '') || ' ' || COALESCE("Category", '') || ' ' || COALESCE("DocumentValue", '')) @@ plainto_tsquery('english', $1)
        ORDER BY rank DESC, "EditedDate" DESC NULLS LAST
        LIMIT 20
        ''',
        search_query,
    )

    if not docs:
        tokens = [t for t in search_query.replace("\n", " ").split(" ") if len(t.strip()) >= 4][:12]
        like_terms = [f"%{t.strip()}%" for t in tokens if t.strip()]
        if like_terms:
            docs = await Database.fetch(
                '''
                SELECT "Id", COALESCE("Title", '') AS title, COALESCE("Category", '') AS category,
                       COALESCE("Version", '') AS version, COALESCE("DocumentValue", '') AS document_value,
                       0.0::float AS rank
                FROM "Document"
                WHERE COALESCE("Title", '') ILIKE ANY($1::text[])
                   OR COALESCE("Category", '') ILIKE ANY($1::text[])
                   OR COALESCE("DocumentValue", '') ILIKE ANY($1::text[])
                ORDER BY "EditedDate" DESC NULLS LAST
                LIMIT 20
                ''',
                like_terms,
            )

    terms = [t.strip().lower() for t in search_query.split(" ") if t.strip()]
    chunks = [
        group._extract_relevant_section(str(r["document_value"]), terms, section_size=700)
        for r in docs
    ]

    print("search_query=", search_query)
    print("docs_found=", len(docs))
    print("first_10_doc_ids=", [int(r["Id"]) for r in docs[:10]])
    print("non_empty_chunks=", sum(1 for c in chunks if c.strip()))

    context = []
    for r, c in zip(docs, chunks):
        context.append(
            f"[Document Id: {int(r['Id'])}] Title: {r['title']}\\n"
            f"Category: {r['category']}\\n"
            f"Version: {r['version']}\\n"
            f"Relevant section:\\n{c[:700]}"
        )

    prompt = (
        "You are a policy locator. Use ONLY the provided document excerpts from the database. "
        "Do not use prior knowledge, web data, or any source not included below. "
        "Do NOT answer hypothetical scenarios directly (for example, do not state what punishment would happen). "
        "Do NOT infer outcomes, discipline, or consequences that are not explicitly written in the excerpts. "
        "Instead, identify the most relevant policies and explain why each is relevant to the user's question.\\n\\n"
        "Response format rules:\\n"
        "1) Start with: Relevant policies\\n"
        "2) Return 1-4 bullet lines in this exact style: - Doc <id> | <title> | relevance: <short reason>\\n"
        "3) If no excerpt directly addresses the question, include: - No direct policy match found in provided excerpts.\\n"
        "4) Optionally add one final line starting with: Clarify: <question> if the policy text is ambiguous\\n"
        "5) If excerpts are insufficient, reply exactly: I can only answer from the Document table and the provided excerpts are insufficient.\\n\\n"
        f"User question:\\n{q}\\n\\n"
        "Document excerpts:\\n"
        + "\\n\\n---\\n\\n".join(context)
    )

    provider = get_provider("ollama")(endpoint="http://localhost:11434/v1")
    out = await provider.complete(prompt)
    print("model_output_preview=")
    print(out[:1000])

    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
