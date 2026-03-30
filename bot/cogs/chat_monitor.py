"""Chat monitor cog.

Watches configured Discord text channels in real time. When a message
contains a ``?``, the bot searches the Document table for relevant
convention information (program book, schedules, meal plans, etc.) and
replies with an AI-generated answer.

Configuration (.env):
    CHAT_MONITOR_CHANNELS        Comma-separated channel names or IDs to
                                 monitor.  Empty = feature disabled.
    CHAT_MONITOR_DOC_CATEGORIES  Comma-separated Document.Category values to
                                 restrict the search to.  Empty = search all
                                 documents.
    CHAT_MONITOR_COOLDOWN_SECONDS Minimum seconds between bot replies in the
                                 same channel (default 30).

Discord prerequisite:
    "Message Content Intent" must be enabled in the Discord Developer Portal
    (Applications → <your bot> → Bot → Privileged Gateway Intents) AND the
    DISCORD_INTENTS_MESSAGE_CONTENT setting must be true.
"""

import asyncio
import logging
import re
import time

import discord
from discord.ext import commands

from ai.provider import get_provider
from config.settings import get_settings
from services.document_search_service import (
    extract_query_terms,
    extract_relevant_sections,
    search_documents,
)

settings = get_settings()

_POLICY_URL_PREFIX = "https://staff.animenebraskon.com/staff/policy/"
_EMBED_COLOR = discord.Color.blurple()
_MAX_EMBED_FIELD = 1024
_MAX_ANSWER_LEN = 900
_DEFAULT_MAX_QUESTION_CHARS = 600

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"developer\s+mode", re.IGNORECASE),
    re.compile(r"reveal\s+.*(system|prompt)", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|guardrails?)", re.IGNORECASE),
    re.compile(r"repeat\s+the\s+text\s+above", re.IGNORECASE),
)

_SUSPICIOUS_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"you\s+are\s+a\s+helpful\s+assistant", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"api[_\s-]?key", re.IGNORECASE),
)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _linkify_doc_lines(answer: str) -> str:
    """Turn ``- Doc <id> | <title> | relevance: …`` into a Markdown hyperlink."""
    pattern = re.compile(
        r"^- Doc\s+(\d+)\s+\|\s*([^|]+?)\s*\|\s*relevance:\s*(.*)$", re.MULTILINE
    )

    def _replace(match: re.Match[str]) -> str:
        doc_id = match.group(1)
        title = match.group(2).strip()
        relevance = match.group(3).strip()
        if title.startswith("[") and "](" in title:
            return match.group(0)
        url = f"{_POLICY_URL_PREFIX}{doc_id}"
        return f"- Doc {doc_id} | [{title}]({url}) | relevance: {relevance}"

    return pattern.sub(_replace, answer)


def _parse_csv(value: str) -> list[str]:
    """Split a comma-separated settings string into a cleaned list."""
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _looks_like_prompt_injection(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    return any(pattern.search(sample) for pattern in _INJECTION_PATTERNS)


def _sanitize_answer_text(text: str) -> str:
    """Reduce mention abuse and obvious markdown/html payload tricks in model output."""
    cleaned = (text or "").replace("\r", "")
    cleaned = cleaned.replace("@everyone", "@\u200beveryone")
    cleaned = cleaned.replace("@here", "@\u200bhere")
    cleaned = re.sub(r"<@&\d+>", "[role mention removed]", cleaned)
    cleaned = re.sub(r"<script.*?>.*?</script>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def _output_looks_sensitive(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    return any(pattern.search(sample) for pattern in _SUSPICIOUS_OUTPUT_PATTERNS)


class ChatMonitorCog(commands.Cog):
    """Listens for messages with '?' in monitored channels and answers from docs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._enabled = bool(getattr(settings, "CHAT_MONITOR_ENABLED", True))
        self._monitored_channel_ids: set[int] = set()
        self._category_filter: list[str] = _parse_csv(
            getattr(settings, "CHAT_MONITOR_DOC_CATEGORIES", "")
        )
        raw_cooldown = int(getattr(settings, "CHAT_MONITOR_COOLDOWN_SECONDS", 30))
        self._cooldown_seconds: int = max(0, raw_cooldown)
        raw_user_cooldown = int(getattr(settings, "CHAT_MONITOR_USER_COOLDOWN_SECONDS", 20))
        self._user_cooldown_seconds: int = max(0, raw_user_cooldown)
        self._max_question_chars = max(
            120,
            int(getattr(settings, "CHAT_MONITOR_MAX_QUESTION_CHARS", _DEFAULT_MAX_QUESTION_CHARS)),
        )
        self._inference_timeout_seconds = max(
            10,
            int(getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 120)),
        )
        self._inference_semaphore = asyncio.Semaphore(
            max(1, int(getattr(settings, "AI_MAX_CONCURRENT_REQUESTS", 2)))
        )
        self._cooldowns: dict[int, float] = {}  # channel_id -> last-reply monotonic time
        self._user_cooldowns: dict[int, float] = {}  # user_id -> last-reply monotonic time
        self._raw_channels: list[str] = _parse_csv(
            getattr(settings, "CHAT_MONITOR_CHANNELS", "")
        )

        if not self._enabled:
            logging.info("ChatMonitor: disabled by CHAT_MONITOR_ENABLED=false")
            return

        if not self._raw_channels:
            logging.info("ChatMonitor: CHAT_MONITOR_CHANNELS is empty — feature disabled.")
        else:
            logging.info(
                "ChatMonitor: configured to watch channels %s (will resolve on ready).",
                self._raw_channels,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._resolve_channels()

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        await self._resolve_channels()

    async def _resolve_channels(self) -> None:
        """Map channel names / IDs from settings to actual channel IDs."""
        if not self._enabled:
            return

        if not self._raw_channels:
            return

        resolved: set[int] = set()
        for guild in self.bot.guilds:
            for spec in self._raw_channels:
                # Try numeric ID first
                channel: discord.abc.GuildChannel | None = None
                if spec.isdigit():
                    channel = guild.get_channel(int(spec))
                else:
                    # Name match (case-insensitive, dashes/underscores interchangeable)
                    normalized = spec.lower().replace("-", "_")
                    for ch in guild.text_channels:
                        if ch.name.lower().replace("-", "_") == normalized:
                            channel = ch
                            break

                if channel and isinstance(channel, discord.TextChannel):
                    resolved.add(channel.id)

        self._monitored_channel_ids = resolved

        if resolved:
            names = [
                f"#{ch.name}"
                for guild in self.bot.guilds
                for ch in guild.text_channels
                if ch.id in resolved
            ]
            logging.info("ChatMonitor: watching channels: %s", names)
        else:
            logging.warning(
                "ChatMonitor: none of the configured channels %s could be resolved.",
                self._raw_channels,
            )

    # ------------------------------------------------------------------
    # Message listener
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self._enabled:
            return

        # Ignore bots (including ourselves)
        if message.author.bot:
            return

        # Only act in monitored channels
        if message.channel.id not in self._monitored_channel_ids:
            return

        # Only respond to messages that contain a question mark
        if "?" not in message.content:
            return

        question = (message.content or "").strip()
        if len(question) > self._max_question_chars:
            logging.debug(
                "ChatMonitor: skipped long question (%s chars) from user_id=%s",
                len(question),
                getattr(message.author, "id", None),
            )
            return

        if _looks_like_prompt_injection(question):
            logging.warning(
                "ChatMonitor: blocked potential injection from user_id=%s channel_id=%s",
                getattr(message.author, "id", None),
                message.channel.id,
            )
            await message.reply(
                "I can help with convention questions, but I can't process that request format.",
                mention_author=False,
            )
            return

        # Per-channel cooldown
        now = time.monotonic()
        last = self._cooldowns.get(message.channel.id, 0.0)
        if now - last < self._cooldown_seconds:
            logging.debug(
                "ChatMonitor: cooldown active in channel %s — skipping.",
                message.channel.id,
            )
            return

        # Per-user cooldown to avoid one user spamming answers across channels.
        user_id = int(getattr(message.author, "id", 0) or 0)
        user_last = self._user_cooldowns.get(user_id, 0.0)
        if now - user_last < self._user_cooldown_seconds:
            logging.debug(
                "ChatMonitor: user cooldown active for user_id=%s — skipping.",
                user_id,
            )
            return

        logging.info(
            "ChatMonitor: question detected in #%s from %s: %r",
            getattr(message.channel, "name", message.channel.id),
            message.author,
            message.content[:120],
        )

        # Update cooldown before the async work so concurrent messages don't
        # all slip through while the first is being answered.
        self._cooldowns[message.channel.id] = now
        self._user_cooldowns[user_id] = now

        await self._handle_question(message)

    # ------------------------------------------------------------------
    # Q&A pipeline
    # ------------------------------------------------------------------

    async def _handle_question(self, message: discord.Message) -> None:
        question = message.content.strip()

        async with message.channel.typing():
            docs = await search_documents(
                question,
                category_filter=self._category_filter or None,
            )

        if not docs:
            logging.info(
                "ChatMonitor: no documents matched for question in #%s: %r",
                getattr(message.channel, "name", message.channel.id),
                question[:120],
            )
            await message.reply(
                "I couldn't find relevant convention information for that question. "
                "Check the program book or ask a staff member for help!",
                mention_author=False,
            )
            return

        # Build AI prompt
        question_terms = extract_query_terms(question)
        context_chunks: list[str] = []
        sources: list[str] = []
        allowed_ids: list[str] = []

        for row in docs:
            doc_id = int(row["Id"])
            title = row.get("title") or "(untitled)"
            category = row.get("category") or "(uncategorized)"
            version = row.get("version") or "(none)"
            excerpt = _truncate(
                extract_relevant_sections(
                    str(row.get("document_value") or ""),
                    question_terms,
                    section_size=420,
                    max_sections=2,
                ),
                900,
            )
            context_chunks.append(
                f"[Document Id: {doc_id}] Title: {title}\n"
                f"Category: {category}\nVersion: {version}\n"
                f"Relevant section:\n{excerpt}"
            )
            sources.append(f"{doc_id}:{title}")
            allowed_ids.append(str(doc_id))

        prompt = (
            "You are a helpful convention information assistant. "
            "Answer the attendee's question using ONLY the provided document excerpts. "
            "Do not use prior knowledge or information not found in the excerpts below. "
            "Be friendly, concise, and direct. If multiple documents are relevant, summarise "
            "the key points from each. If the excerpts do not contain enough information to "
            "answer the question, say so clearly and suggest the attendee contact staff.\n\n"
            "Response format:\n"
            "1) Give a direct, conversational answer (2-5 sentences).\n"
            "2) Optionally list 1-3 source lines: - Doc <id> | <title> | relevance: <short reason>\n"
            "3) If the excerpts are insufficient, reply: "
            "I don't have enough information in my documents to answer that. Please ask a staff member!\n\n"
            f"Only cite document IDs from this allowed list: {', '.join(allowed_ids)}\n\n"
            f"Question: {question}\n\n"
            "Document excerpts:\n"
            + "\n\n---\n\n".join(context_chunks)
        )

        provider_name = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()
        provider_cls = get_provider(provider_name)
        if not provider_cls:
            logging.error("ChatMonitor: AI provider %r not registered.", provider_name)
            await message.reply(
                "Convention Q&A is temporarily unavailable (AI provider not configured).",
                mention_author=False,
            )
            return

        try:
            try:
                provider = provider_cls(endpoint=settings.AI_ENDPOINT)
            except TypeError:
                provider = provider_cls()

            async def _run_inference() -> str:
                async with self._inference_semaphore:
                    return await provider.complete(prompt)

            answer = await asyncio.wait_for(
                _run_inference(),
                timeout=self._inference_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logging.warning(
                "ChatMonitor: inference timed out after %ss in channel_id=%s",
                self._inference_timeout_seconds,
                message.channel.id,
            )
            await message.reply(
                "I took too long to answer (the model may be waking up or busy). "
                "Please try again in a moment.",
                mention_author=False,
            )
            return
        except Exception:
            logging.exception("ChatMonitor: AI completion failed")
            await message.reply(
                "I ran into a problem generating an answer. Please ask a staff member!",
                mention_author=False,
            )
            return

        raw_answer = (answer or "").strip() or "(no response)"
        raw_answer = _sanitize_answer_text(raw_answer)
        if _output_looks_sensitive(raw_answer):
            logging.warning(
                "ChatMonitor: blocked suspicious model output in channel_id=%s",
                message.channel.id,
            )
            await message.reply(
                "I couldn't safely answer that from approved sources. Please ask a staff member.",
                mention_author=False,
            )
            return

        raw_answer = _linkify_doc_lines(raw_answer)
        safe_answer = _truncate(raw_answer, _MAX_ANSWER_LEN)
        source_line = _truncate(", ".join(sources), 256)

        embed = discord.Embed(
            title="Convention Q&A",
            description=safe_answer,
            color=_EMBED_COLOR,
        )
        embed.set_footer(text=f"Sources: {source_line}")

        logging.info(
            "ChatMonitor: answered question in #%s: %r → %r",
            getattr(message.channel, "name", message.channel.id),
            question[:120],
            safe_answer[:120],
        )

        await message.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatMonitorCog(bot))
