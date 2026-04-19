import re

with open("bot/cogs/staffninja.py", "r") as f:
    content = f.read()

# Replace imports
content = re.sub(
    r'import secrets\nimport smtplib\nfrom email\.message import EmailMessage\n\nimport discord\nfrom discord import app_commands\nfrom discord\.ext import commands\n\nfrom ai\.provider import get_provider\nfrom config\.settings import get_settings\nfrom db\.connection import Database',
    r'import discord\nfrom discord import app_commands\nfrom discord.ext import commands\n\nfrom ai.provider import get_provider\nfrom config.settings import get_settings\nimport db.queries\nimport services.staffninja_service as sns',
    content
)

# Replace staticmethods
content = re.sub(
    r'    @staticmethod\n    def _format_event_timestamp.*?    @app_commands\.command\(name="server"',
    r'    @app_commands.command(name="server"',
    content,
    flags=re.DOTALL
)

# Replace server
content = re.sub(
    r'    @app_commands\.command\(name="server".*?await self\._finish_slash_response\(interaction, content="\\n"\.join\(lines\)\)\n',
    r'''    @app_commands.command(name="server", description="Show private bot/server health status")
    async def server(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        latency_ms = int((interaction.client.latency or 0) * 1000)
        content = await sns.get_server_status_text(latency_ms, interaction.client.launch_time)
        await self._finish_slash_response(interaction, content=content)
''',
    content,
    flags=re.DOTALL,
    count=1
)

# Replace event
content = re.sub(
    r'    @app_commands\.command\(name="event".*?await self\._finish_slash_response\(interaction, content="\\n"\.join\(lines\)\)\n',
    r'''    @app_commands.command(name="event", description="Show event status and related metrics")
    async def event(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        content = await sns.get_formatted_event_status()
        await self._finish_slash_response(interaction, content=content)
''',
    content,
    flags=re.DOTALL,
    count=1
)

# Replace link
content = re.sub(
    r'    @app_commands\.command\(name="link".*?await self\._finish_slash_response\(\n            interaction,\n            content="Verification code sent\. Run `/staffninja verify code:<123456>` to complete linking\.",\n        \)\n',
    r'''    @app_commands.command(name="link", description="Link your Discord account to your staff record by email")
    @app_commands.describe(email="Email address on your staff record")
    async def link(self, interaction: discord.Interaction, email: str):
        await self._begin_slash_response(interaction)
        res = await sns.init_link_process(email, str(interaction.user.id))
        if res["success"]:
            self.pending_link_challenges[int(interaction.user.id)] = res["pending_data"]
        await self._finish_slash_response(interaction, content=res["message"])
''',
    content,
    flags=re.DOTALL,
    count=1
)

# Replace verify
content = re.sub(
    r'    @app_commands\.command\(name="verify".*?Your Discord account has been linked successfully\. You can now run `/staffninja status`\.",\n        \)\n',
    r'''    @app_commands.command(name="verify", description="Verify your email code and complete account linking")
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
''',
    content,
    flags=re.DOTALL,
    count=1
)

# Replace status (staff)
content = re.sub(
    r'    @app_commands\.command\(name="status".*?await self\._finish_slash_response\(interaction, content="\\n"\.join\(lines\)\)\n',
    r'''    @app_commands.command(name="status", description="Show your staff profile and status")
    async def staff(self, interaction: discord.Interaction):
        await self._begin_slash_response(interaction)
        content = await sns.get_formatted_staff_profile(interaction.user)
        await self._finish_slash_response(interaction, content=content)
''',
    content,
    flags=re.DOTALL,
    count=1
)

# Replace policy DB fetch logic
content = re.sub(
    r'        used_fallback = False\n        like_terms: list\[str\] = \[\]\n        query_candidates = \[q for q in \[clean_question, search_query\] if q and q\.strip\(\)\]\n        deduped_queries: list\[str\] = \[\]\n        seen_queries = set\(\)\n        for q in query_candidates:\n            normalized = q\.strip\(\)\.lower\(\)\n            if normalized not in seen_queries:\n                seen_queries\.add\(normalized\)\n                deduped_queries\.append\(q\)\n\n        docs_by_id: dict\[int, dict\] = \{\}\n.*?            return\n\n        def _rank_row\(row: dict\) -> tuple\[float, float\]:',
    r'''        used_fallback = False
        like_terms = []
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

        def _rank_row(row: dict) -> tuple[float, float]:''',
    content,
    flags=re.DOTALL,
    count=1
)

with open("bot/cogs/staffninja.py", "w") as f:
    f.write(content)
