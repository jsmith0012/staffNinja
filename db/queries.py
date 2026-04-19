from db.connection import Database

# --- mailing_lists.py queries ---

async def is_leadership_user(candidates: list[str]) -> bool:
    rows = await Database.fetch(
        """
        SELECT COALESCE(BOOL_OR(sp."LeadershipPosition"), FALSE) AS is_leadership
        FROM "User" u
        INNER JOIN "UserStaffPosition" usp ON usp."UserId" = u."Id"
        INNER JOIN "StaffPosition" sp ON sp."Id" = usp."StaffPositionId"
        WHERE LOWER(TRIM(BOTH '@' FROM COALESCE(u."Discord", ''))) = ANY($1::text[])
        """,
        candidates,
    )
    return bool(rows and rows[0]["is_leadership"])

async def get_user_email_by_discord(candidates: list[str]) -> str | None:
    rows = await Database.fetch(
        """
        SELECT u."Email" AS email
        FROM "User" u
        WHERE LOWER(TRIM(BOTH '@' FROM COALESCE(u."Discord", ''))) = ANY($1::text[])
        LIMIT 1
        """,
        candidates,
    )
    if rows:
        return rows[0]["email"]
    return None

# --- staffninja.py queries ---

async def check_server_health() -> bool:
    rows = await Database.fetch("SELECT 1 AS ok")
    return bool(rows and rows[0]["ok"] == 1)

async def get_active_event_metadata():
    rows = await Database.fetch(
        'SELECT "Id", "Name", "Status", "Start", "End", "EventBriteId", "VenueId", "StaffAgreementFormId" FROM "Event" WHERE "Status" = 1 ORDER BY "Id" DESC LIMIT 1'
    )
    return rows[0] if rows else None

async def get_event_metrics(event_id: int):
    rows = await Database.fetch(
        """
        SELECT
            (SELECT COUNT(*) FROM "AttendeeBadge" WHERE "EventId" = $1) AS attendee_badges,
            (SELECT COUNT(*) FROM "Budget" WHERE "EventId" = $1) AS budgets,
            (SELECT COUNT(*) FROM "Panel" WHERE "EventId" = $1) AS panels,
            (SELECT COUNT(*) FROM "StaffShift" WHERE "EventId" = $1) AS staff_shifts,
            (SELECT COUNT(*) FROM "UserEventPreferences" WHERE "EventId" = $1) AS user_preferences,
            (SELECT COUNT(*) FROM "Transaction" WHERE "EventId" = $1) AS transactions,
            (SELECT COUNT(*) FROM "conExpenseBudget" WHERE "sysEventId" = $1) AS expense_budgets,
            (SELECT COUNT(*) FROM "deprecated_regBadge" WHERE "eventId" = $1) AS legacy_badges,
            (SELECT COUNT(*) FROM "schSchedule" WHERE "sysEventId" = $1) AS schedules,
            (SELECT COUNT(*) FROM "stfEvent" WHERE "eventId" = $1) AS staff_events,
            (SELECT COUNT(*) FROM "volAwarded" WHERE "eventId" = $1) AS volunteer_awards,
            (SELECT COUNT(*) FROM "volHours" WHERE "eventId" = $1) AS volunteer_hours,
            (SELECT COUNT(*) FROM "volRewards" WHERE "eventId" = $1) AS volunteer_rewards
        """,
        event_id,
    )
    return rows[0] if rows else None

async def get_event_venue_name(venue_id: int) -> str | None:
    rows = await Database.fetch(
        'SELECT COALESCE("Name", \'(none)\') AS venue_name FROM "Venue" WHERE "Id" = $1 LIMIT 1',
        venue_id,
    )
    return rows[0]["venue_name"] if rows else None

async def find_user_by_email_for_link(email: str):
    return await Database.fetch(
        'SELECT "Id", COALESCE("Discord", \'\') AS discord_value FROM "User" WHERE LOWER(COALESCE("Email", \'\')) = $1',
        email,
    )

async def update_user_discord_link(discord_id: str, user_id: int) -> str:
    return await Database.execute(
        'UPDATE "User" SET "Discord" = $1 WHERE "Id" = $2 AND COALESCE("Discord", \'\') = \'\'',
        discord_id,
        user_id,
    )

async def get_user_staff_profile(handle_candidates: list[str]):
    query = """
        SELECT
            u."Id" AS user_id,
            COALESCE(u."FirstName", '') AS first_name,
            COALESCE(u."LastName", '') AS last_name,
            COALESCE(u."PreferredFirstName", '') AS preferred_first_name,
            COALESCE(u."PreferredLastName", '') AS preferred_last_name,
            COALESCE(u."Discord", '') AS discord_value,
            u."Email" AS email,
            u."Phone" AS phone,
            u."BirthDate" AS birth_date,
            u."Allergy" AS allergies,
            u."YearJoined" AS year_joined,
            u."Status" AS status_code,
            COALESCE(string_agg(DISTINCT sp."Name", ', '), 'None') AS staff_positions,
            COALESCE(BOOL_OR(sp."LeadershipPosition"), FALSE) AS is_leadership
        FROM "User" u
        LEFT JOIN "UserStaffPosition" usp ON usp."UserId" = u."Id"
        LEFT JOIN "StaffPosition" sp ON sp."Id" = usp."StaffPositionId"
        WHERE LOWER(TRIM(BOTH '@' FROM COALESCE(u."Discord", ''))) = ANY($1::text[])
        GROUP BY u."Id", u."FirstName", u."LastName", u."PreferredFirstName", u."PreferredLastName", u."Discord", u."Email", u."Phone", u."BirthDate", u."Allergy", u."YearJoined", u."Status"
        ORDER BY u."Id"
        LIMIT 1
    """
    rows = await Database.fetch(query, handle_candidates)
    return rows[0] if rows else None

async def get_user_staff_agreements(user_id: int):
    rows = await Database.fetch(
        """
        SELECT
            e."Id" AS event_id,
            COALESCE(e."Name", '') AS event_name,
            e."StaffAgreementFormId" AS staff_agreement_form_id,
            COALESCE(f."Title", '') AS staff_agreement_form_title,
            cf."Id" AS completed_form_id,
            COALESCE(cf."EditedDate", cf."CreatedDate") AS completed_at
        FROM "Event" e
        LEFT JOIN "Form" f ON f."Id" = e."StaffAgreementFormId"
        LEFT JOIN LATERAL (
            SELECT "Id", "EditedDate", "CreatedDate"
            FROM "CompletedForm"
            WHERE "FormId" = e."StaffAgreementFormId"
              AND "UserId" = $1
            ORDER BY COALESCE("EditedDate", "CreatedDate") DESC NULLS LAST, "Id" DESC
            LIMIT 1
        ) cf ON TRUE
        WHERE e."Status" = 1
        ORDER BY e."Id" DESC
        LIMIT 1
        """,
        user_id,
    )
    return rows[0] if rows else None

# --- document_search_service.py queries ---

async def search_documents_stage1(search_candidate: str, category_filter: list[str] | None):
    category_clause = ""
    category_args = []
    if category_filter:
        category_clause = 'AND "Category" = ANY($2::text[])'
        category_args = [category_filter]
        
    return await Database.fetch(
        """
        SELECT
            "Id",
            COALESCE("Title",    '') AS title,
            COALESCE("Category", '') AS category,
            COALESCE("Version",  '') AS version,
            ts_rank_cd(
                to_tsvector(
                    'english',
                    COALESCE("Title", '') || ' ' ||
                    COALESCE("Category", '') || ' ' ||
                    COALESCE("DocumentValue", '')
                ),
                plainto_tsquery('english', $1)
            ) AS rank
        FROM "Document"
        WHERE TRUE {category_clause}
        ORDER BY rank DESC, "EditedDate" DESC NULLS LAST
        """.format(category_clause=category_clause),
        search_candidate,
        *category_args,
    )

async def search_documents_fallback(like_terms: list[str], category_filter: list[str] | None):
    category_clause2 = ""
    category_args2 = []
    if category_filter:
        category_clause2 = 'AND "Category" = ANY($2::text[])'
        category_args2 = [category_filter]

    return await Database.fetch(
        """
        SELECT
            "Id",
            COALESCE("Title",    '') AS title,
            COALESCE("Category", '') AS category,
            COALESCE("Version",  '') AS version,
            0.0::float AS rank
        FROM "Document"
        WHERE (
            COALESCE("Title",          '') ILIKE ANY($1::text[])
         OR COALESCE("Category",       '') ILIKE ANY($1::text[])
         OR COALESCE("DocumentValue",  '') ILIKE ANY($1::text[])
        ) {category_clause2}
        ORDER BY "EditedDate" DESC NULLS LAST
        """.format(category_clause2=category_clause2),
        like_terms,
        *category_args2,
    )

async def search_documents_stage2(deep_ids: list[int]):
    return await Database.fetch(
        """
        SELECT "Id", COALESCE("DocumentValue", '') AS document_value
        FROM "Document"
        WHERE "Id" = ANY($1::int[])
        ORDER BY array_position($1::int[], "Id")
        """,
        deep_ids,
    )
