import asyncio
import re
import logging
import discord
from discord import app_commands
from discord.ext import commands

from ai.provider import get_provider
from config.settings import get_settings
import services.staffninja_service as sns
from jobs.anime_quotes import random_wait_message
from services.document_search_service import (
    extract_query_terms as _svc_extract_query_terms,
    build_search_query as _svc_build_search_query,
    extract_relevant_sections as _svc_extract_relevant_sections,
    search_documents as _svc_search_documents,
)
from services import google_groups_service
from bot.cogs.mailing_lists import _get_user_email, _is_leadership, _build_embed, MailingListView
from utils.errors import GoogleGroupsError

settings = get_settings()


class StaffNinjaGroup(app_commands.Group):
    pending_link_challenges: dict[int, dict] = {}

    def __init__(self):
        super().__init__(name="staffninja", description="staffNinja bot commands")

    async def _begin_slash_response(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.edit_original_response(content=random_wait_message())

    async def _finish_slash_response(
        self,
        interaction: discord.Interaction,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        await interaction.edit_original_response(content=content, embed=embed, view=view)

    @app_commands.command(name="server", description="Show private bot/server health status")
    async def server(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        latency_ms = int((interaction.client.latency or 0) * 1000)
        content = await sns.get_server_status_text(latency_ms, interaction.client.launch_time)
        await self._finish_slash_response(interaction, content=content)

    @app_commands.command(name="jobs", description="Show job queue status and recent failures")
    async def jobs(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)

        from jobs.queue import job_counts, recent_failed
        from jobs.handlers import registered_types

        counts = await job_counts()
        total = sum(counts.values())

        lines = [
            "**Job Queue Status**",
            f"- Pending: **{counts.get('pending', 0)}**",
            f"- Running: **{counts.get('running', 0)}**",
            f"- Completed: **{counts.get('completed', 0)}**",
            f"- Failed: **{counts.get('failed', 0)}**",
            f"- Total: **{total}**",
            f"- Registered handlers: {', '.join(registered_types()) or '(none)'}",
        ]

        failed = await recent_failed(limit=5)
        if failed:
            lines.append("\n**Recent Failures:**")
            for j in failed:
                err_preview = (j.error or "unknown")[:80]
                ts = j.completed_at.strftime("%m-%d %H:%M") if j.completed_at else "?"
                lines.append(f"  `#{j.id}` {j.job_type} ({ts}) — {err_preview}")

        await self._finish_slash_response(interaction, content="\n".join(lines))

    @app_commands.command(name="help", description="Show available slash commands")
    async def help(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)

        lines = [
            "staffNinja slash command help",
            "- /staffninja server: private health report for bot/server/db status",
            "- /staffninja help: this command list",
            "- /staffninja status: your staff profile/status from the User table",
            "- /staffninja event: active event status and related metrics",
            "- /staffninja jobs: job queue status and recent failures",
            "- /staffninja policy <question>: answers from Document table excerpts only",
            "- /staffninja link email:<you@example.com>: sends a verification code to your email",
            "- /staffninja verify code:<123456>: verifies code and links your Discord account",
        ]
        await self._finish_slash_response(interaction, content="\n".join(lines))

    @app_commands.command(name="event", description="Show event status and related metrics")
    async def event(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        content = await sns.get_formatted_event_status()
        await self._finish_slash_response(interaction, content=content)

    @app_commands.command(name="link", description="Link your Discord account to your staff record by email")
    @app_commands.describe(email="Email address on your staff record")
    async def link(self, interaction: discord.Interaction, email: str):
        await self._begin_slash_response(interaction)
        res = await sns.init_link_process(email, str(interaction.user.id))
        if res["success"]:
            self.pending_link_challenges[int(interaction.user.id)] = res["pending_data"]
        await self._finish_slash_response(interaction, content=res["message"])

    @app_commands.command(name="verify", description="Verify your email code and complete account linking")
    @app_commands.describe(code="6-digit code sent to your email")
    async def verify(self, interaction: discord.Interaction, code: str):
        await self._begin_slash_response(interaction)

        user_id = int(interaction.user.id)
        requestor_id = str(interaction.user.id)
        pending = self.pending_link_challenges.get(user_id)

        if not pending:
            await self._finish_slash_response(
                interaction,
                content="No pending link request found. Run `/staffninja link` first.",
            )
            return

        res = await sns.verify_link_code(code, requestor_id, pending)
        if res.get("remove_pending"):
            self.pending_link_challenges.pop(user_id, None)

        await self._finish_slash_response(interaction, content=res["message"])

    @app_commands.command(name="status", description="Show your staff profile and status")
    async def staff(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        content = await sns.get_formatted_staff_profile(interaction.user)
        await self._finish_slash_response(interaction, content=content)


    # ---- mailing list command ----

    @app_commands.command(name="mailinglist", description="View and manage your mailing list subscriptions")
    async def mailinglist(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)

        email = await _get_user_email(interaction.user)
        if not email:
            await self._finish_slash_response(
                interaction,
                content=(
                    "Your Discord account is not linked to a staff record. "
                    "Use `/staffninja link` to connect your account first."
                ),
            )
            return

        allowed = google_groups_service.get_allowed_groups()
        if not allowed:
            await self._finish_slash_response(
                interaction,
                content="No mailing lists are configured. Contact an admin.",
            )
            return

        try:
            groups = await google_groups_service.get_user_groups(email)
        except GoogleGroupsError as exc:
            await self._finish_slash_response(
                interaction,
                content=f"Failed to retrieve mailing lists: {exc}",
            )
            return

        # Hide leadership-only mailing list from non-leaders
        leadership_group = (settings.MAILINGLIST_LEADERSHIP_GROUP or "").strip().lower()
        if leadership_group:
            is_leader = await _is_leadership(interaction.user)
            if not is_leader:
                groups = [g for g in groups if g["email"] != leadership_group]

        embed = _build_embed(groups)
        view = MailingListView(invoker_id=interaction.user.id, user_email=email, groups=groups)
        await self._finish_slash_response(interaction, content=None, embed=embed, view=view)

    # ---- policy command (formerly /eventninja policy) ----

    POLICY_URL_PREFIX = "https://staff.animenebraskon.com/staff/policy/"
    POLICY_DEEP_ANALYZE_LIMIT = 40
    POLICY_CONTEXT_LIMIT = 16

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    @staticmethod
    def _extract_relevant_section(text: str, terms: list[str], section_size: int = 700) -> str:
        if not text:
            return ""

        compact = str(text).replace("\r", "")
        lowered = compact.lower()
        match_positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]

        if not match_positions:
            return compact[:section_size]

        first_match = min(match_positions)
        start = max(0, first_match - (section_size // 3))
        end = min(len(compact), start + section_size)
        return compact[start:end]

    @staticmethod
    def _extract_relevant_sections(text: str, terms: list[str], section_size: int = 420, max_sections: int = 2) -> str:
        return _svc_extract_relevant_sections(text, terms, section_size=section_size, max_sections=max_sections)

    @staticmethod
    def _extract_query_terms(question: str) -> list[str]:
        return _svc_extract_query_terms(question)

    @staticmethod
    def _build_policy_search_query(question: str) -> str:
        return _svc_build_search_query(question)

    @classmethod
    def _linkify_policy_lines(cls, answer: str) -> str:
        pattern = re.compile(r"^- Doc\s+(\d+)\s+\|\s*([^|]+?)\s*\|\s*relevance:\s*(.*)$", re.MULTILINE)

        def _replace(match: re.Match[str]) -> str:
            doc_id = match.group(1)
            title = match.group(2).strip()
            relevance = match.group(3).strip()

            if title.startswith("[") and "](" in title:
                return match.group(0)

            policy_url = f"{cls.POLICY_URL_PREFIX}{doc_id}"
            return f"- Doc {doc_id} | [{title}]({policy_url}) | relevance: {relevance}"

        return pattern.sub(_replace, answer)

    @app_commands.command(name="policy", description="Answer policy questions from Document table content")
    @app_commands.describe(question="Policy question to answer from documents")
    async def policy(self, interaction: discord.Interaction, question: str):
        await self._begin_slash_response(interaction)

        clean_question = (question or "").strip()
        search_query = self._build_policy_search_query(clean_question)
        question_terms = self._extract_query_terms(clean_question)
        score_terms = question_terms or self._extract_query_terms(search_query)
        user_id = getattr(interaction.user, "id", None)
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id

        logging.info(
            "Policy question received: user_id=%s guild_id=%s channel_id=%s question=%s",
            user_id,
            guild_id,
            channel_id,
            clean_question,
        )

        if not clean_question:
            logging.info(
                "Policy question rejected (empty input): user_id=%s guild_id=%s channel_id=%s",
                user_id,
                guild_id,
                channel_id,
            )
            await self._finish_slash_response(
                interaction,
                content="Please provide a policy question.",
            )
            return

        provider_name = (settings.AI_PROVIDER or "").strip().lower()
        use_ai = provider_name not in ("db_search", "none", "disabled")
        provider_cls = None
        if use_ai:
            provider_cls = get_provider(provider_name)
            if not provider_cls:
                logging.error(
                    "Policy question failed: provider not registered user_id=%s provider=%s",
                    user_id,
                    provider_name,
                )
                await self._finish_slash_response(
                    interaction,
                    content=f"AI provider '{provider_name}' is not registered.",
                )
                return

        logging.debug(
            "Policy search initialized: user_id=%s provider=%s search_query=%s",
            user_id,
            provider_name,
            search_query,
        )

        try:
            docs_with_text = await _svc_search_documents(
                question=clean_question,
                deep_limit=self.POLICY_DEEP_ANALYZE_LIMIT,
                context_limit=self.POLICY_CONTEXT_LIMIT
            )
            if not docs_with_text:
                await self._finish_slash_response(
                    interaction,
                    content="I can only answer from the Document table and found no matching policy text.",
                )
                return
        except Exception as exc:
            logging.exception("Policy document lookup failed")
            await self._finish_slash_response(
                interaction,
                content=f"Document lookup failed: {exc.__class__.__name__}",
            )
            return

        policy_scan_count = len(docs_with_text)
        deep_candidates = docs_with_text

        def _rank_row(row: dict) -> tuple[float, float]:
            title = (row.get("title") or "").lower()
            category = (row.get("category") or "").lower()
            text = str(row.get("document_value") or "").lower()
            base_rank = float(row.get("rank") or 0.0)

            overlap_count = sum(1 for t in score_terms if t in text)
            title_hits = sum(1 for t in score_terms if t in title)
            category_hits = sum(1 for t in score_terms if t in category)

            score = (base_rank * 10.0) + (overlap_count * 2.0) + (title_hits * 3.0) + (category_hits * 2.0)
            return score, base_rank

        docs = sorted(docs_with_text, key=_rank_row, reverse=True)[: self.POLICY_CONTEXT_LIMIT]

        search_terms = score_terms
        context_chunks = []
        sources = []
        allowed_doc_ids = []
        doc_debug_rows = []
        for row in docs:
            doc_id = int(row["Id"])
            title = row["title"] or "(untitled)"
            category = row["category"] or "(uncategorized)"
            version = row["version"] or "(none)"
            excerpt = self._truncate(
                self._extract_relevant_sections(str(row["document_value"]), search_terms, section_size=420, max_sections=2),
                900,
            )
            context_chunks.append(
                f"[Document Id: {doc_id}] Title: {title}\nCategory: {category}\nVersion: {version}\nRelevant section:\n{excerpt}"
            )
            sources.append(f"{doc_id}:{title}")
            allowed_doc_ids.append(str(doc_id))
            doc_debug_rows.append(
                {
                    "id": doc_id,
                    "title": title,
                    "category": category,
                    "version": version,
                    "rank": float(row["rank"]) if row["rank"] is not None else None,
                    "score_terms": score_terms,
                    "document_len": len(str(row["document_value"])),
                    "chunk_len": len(excerpt),
                }
            )

        logging.debug(
            "Policy context prepared: user_id=%s scanned=%s deep_candidates=%s context_docs=%s used_fallback=%s docs=%s",
            user_id,
            policy_scan_count,
            len(deep_candidates),
            len(docs),
            doc_debug_rows,
        )

        if use_ai:
            prompt = (
                "You are a policy locator. Use ONLY the provided document excerpts from the database. "
                "Do not use prior knowledge, web data, or any source not included below. "
                "Do NOT answer hypothetical scenarios directly (for example, do not state what punishment would happen). "
                "Do NOT infer outcomes, discipline, or consequences that are not explicitly written in the excerpts. "
                "Instead, identify the most relevant policies and explain why each is relevant to the user's question. "
                "Prefer policies with explicit language that directly matches the question's intent or terms.\n\n"
                "Response format rules:\n"
                "1) Start with: Relevant policies\n"
                "2) Return 1-4 bullet lines in this exact style: - Doc <id> | <title> | relevance: <short reason>\n"
                "3) Each reason must reference concrete wording from the excerpt (not generic guesses).\n"
                "4) If no excerpt directly addresses the question, include: - No direct policy match found in provided excerpts.\n"
                "5) Optionally add one final line starting with: Clarify: <question> if the policy text is ambiguous\n"
                "6) If excerpts are insufficient, reply exactly: I can only answer from the Document table and the provided excerpts are insufficient.\n\n"
                f"Only use document IDs from this allowed list when citing: {', '.join(allowed_doc_ids)}\n\n"
                f"Question key terms: {', '.join(score_terms) if score_terms else '(none)'}\n\n"
                f"User question:\n{clean_question}\n\n"
                "Document excerpts:\n"
                + "\n\n---\n\n".join(context_chunks)
            )

            logging.debug(
                "Policy prompt prepared: user_id=%s prompt_chars=%s allowed_doc_ids=%s",
                user_id,
                len(prompt),
                allowed_doc_ids,
            )

            try:
                try:
                    provider = provider_cls(endpoint=settings.AI_ENDPOINT)
                except TypeError:
                    provider = provider_cls()

                inference_timeout = max(10, int(getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 120)))
                answer = await asyncio.wait_for(provider.complete(prompt), timeout=inference_timeout)
                logging.debug(
                    "Policy AI completion succeeded: user_id=%s raw_answer_chars=%s",
                    user_id,
                    len((answer or "")),
                )
            except asyncio.TimeoutError:
                logging.warning(
                    "Policy AI completion timed out: user_id=%s timeout=%ss",
                    user_id,
                    int(getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 120)),
                )
                await self._finish_slash_response(
                    interaction,
                    content=(
                        "That request took too long (the model may be loading or under heavy use). "
                        "Please try again in a moment."
                    ),
                )
                return
            except Exception as exc:
                logging.exception("Policy AI completion failed")
                await self._finish_slash_response(
                    interaction,
                    content=f"AI policy response failed: {exc.__class__.__name__}",
                )
                return

            final_answer = self._truncate((answer or "").strip() or "(no response)", 1600)
        else:
            # ---- db_search mode: format results directly (no LLM) ----
            bullets = []
            for row in docs[:4]:
                doc_id = int(row["Id"])
                title = row.get("title") or "(untitled)"
                snippet = self._extract_relevant_sections(
                    str(row.get("document_value", "")), search_terms,
                    section_size=200, max_sections=1,
                )
                # Use a concise snippet as the relevance reason
                reason = snippet.replace("\n", " ").strip()
                reason = self._truncate(reason, 120) if reason else "matches search terms"
                bullets.append(f"- Doc {doc_id} | {title} | relevance: {reason}")
            final_answer = "Relevant policies\n" + "\n".join(bullets)
            logging.info(
                "Policy db_search completed: user_id=%s results=%s",
                user_id, len(bullets),
            )
        final_answer = self._linkify_policy_lines(final_answer)
        source_line = self._truncate(", ".join(sources), 500)
        safe_question = self._truncate(clean_question, 300)
        template_header = "eventNinja policy matches"
        template_question = f"- question: {safe_question}"
        template_scan = f"- policy scan: scanned {policy_scan_count} total, analyzed {len(deep_candidates)} deeply, cited from {len(docs)}"
        template_sources = f"- source documents: {source_line}"
        fixed_size = len(template_header) + len(template_question) + len(template_scan) + len(template_sources) + len("- relevant policies:\n") + 12
        max_answer_len = max(200, 1900 - fixed_size)
        safe_answer = self._truncate(final_answer, max_answer_len)

        lines = [
            template_header,
            template_question,
            f"- relevant policies:\n{safe_answer}",
            #template_scan,
            #template_sources,
        ]
        combined = "\n".join(lines)
        if len(combined) > 1900:
            overflow = len(combined) - 1900
            safe_answer = self._truncate(safe_answer, max(200, len(safe_answer) - overflow - 5))
            lines = [
                template_header,
                template_question,
                f"- relevant policies:\n{safe_answer}",
                template_scan,
                template_sources,
            ]

        logging.info(
            "Policy response sent: user_id=%s guild_id=%s channel_id=%s question=%s response=%s",
            user_id,
            guild_id,
            channel_id,
            safe_question,
            safe_answer,
        )
        await self._finish_slash_response(interaction, content="\n".join(lines))


class StaffNinjaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = StaffNinjaGroup()
        self.bot.tree.add_command(self.group)

    def cog_unload(self):
        self.bot.tree.remove_command(self.group.name, type=self.group.type)


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffNinjaCog(bot))
