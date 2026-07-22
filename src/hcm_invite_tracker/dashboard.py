from __future__ import annotations

import base64
import hmac
import html
from datetime import UTC, datetime

from aiohttp import web

from .config import Settings
from .database import Database
from .website import render_website_mapping



class Dashboard:
    def __init__(self, db: Database, settings: Settings, project_name: str):
        self.db = db
        self.settings = settings
        self.project_name = project_name
        self.runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application(middlewares=[self._security_headers, self._basic_auth])
        app.router.add_get("/healthz", self.health)
        app.router.add_get("/", self.index)
        app.router.add_get("/exports/joins.csv", self.joins_csv)
        app.router.add_get("/exports/invites.csv", self.invites_csv)
        app.router.add_get("/exports/discord-invites.yml", self.website_yaml)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(
            self.runner,
            host=self.settings.dashboard_host,
            port=self.settings.dashboard_port,
        )
        await site.start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    @web.middleware
    async def _security_headers(self, request: web.Request, handler):
        response = await handler(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers[
            "Content-Security-Policy"
        ] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @web.middleware
    async def _basic_auth(self, request: web.Request, handler):
        if request.path == "/healthz":
            return await handler(request)
        username = self.settings.dashboard_username
        password = self.settings.dashboard_password
        if not username or not password:
            return await handler(request)
        supplied = request.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        if not hmac.compare_digest(supplied, expected):
            raise web.HTTPUnauthorized(
                headers={"WWW-Authenticate": 'Basic realm="Invite Tracker"'}
            )
        return await handler(request)

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "project": self.project_name,
                "total_joins": self.db.total_joins(),
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )

    async def index(self, request: web.Request) -> web.Response:
        summary = self.db.source_summary()
        recent = self.db.recent_joins(30)
        invites = self.db.list_invites(active_only=True)
        source_rows = "".join(
            "<tr>"
            f"<td>{_e(row['source_slug'])}</td>"
            f"<td>{row['join_count']}</td>"
            f"<td>{row['normal_count']}</td>"
            f"<td>{_e(row['latest_join'] or '—')}</td>"
            "</tr>"
            for row in summary
        ) or '<tr><td colspan="4">No joins recorded yet.</td></tr>'
        recent_rows = "".join(
            "<tr>"
            f"<td>{_e(row['recorded_at'])}</td>"
            f"<td>{_e(row['member_name'] or '[identity purged]')}</td>"
            f"<td>{_e(row['source_slug'] or 'unknown')}</td>"
            f"<td>{_e(row['invite_code'] or 'unknown')}</td>"
            f"<td>{_e(row['confidence'])}</td>"
            "</tr>"
            for row in recent
        ) or '<tr><td colspan="5">No joins recorded yet.</td></tr>'
        invite_rows = "".join(
            "<tr>"
            f"<td>{_e(row['source_slug'] or 'unmapped')}</td>"
            f"<td>{_e(row['code'])}</td>"
            f"<td>{_e(row['source_type'])}</td>"
            f"<td>{row['uses']}</td>"
            f"<td>{_e(row['channel_name'] or 'unknown')}</td>"
            f"<td>{_e(row['inviter_name'] or 'unknown')}</td>"
            "</tr>"
            for row in invites
        ) or '<tr><td colspan="6">No active invites visible.</td></tr>'

        body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(self.project_name)} Invite Tracker</title>
<style>
:root{{--bg:#080a09;--panel:#111819;--text:#e7d8b5;--soft:#b8ad91;--blue:#a9bdd1;--green:#5f7f68;--border:#314354}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(#101820,#080a09);color:var(--text);font:15px/1.5 system-ui,sans-serif}}
main{{width:min(1180px,calc(100% - 32px));margin:auto;padding:38px 0 70px}} h1,h2{{font-family:Georgia,serif}} h1{{font-size:clamp(2rem,5vw,3.5rem);margin:0}} h2{{margin-top:34px;color:#f4e8c1}}
p{{color:var(--soft)}} .stats{{display:flex;gap:14px;flex-wrap:wrap}} .stat{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 18px}}
a{{color:var(--blue)}} .table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:12px;background:var(--panel)}} table{{border-collapse:collapse;width:100%}} th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}} th{{color:var(--blue)}}
code{{color:#f4e8c1}} .exports{{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}}
</style></head><body><main>
<h1>{_e(self.project_name)} Invite Tracker</h1>
<p>Local administrative view. Invite attribution is inferred from Discord use-counter changes and is not guaranteed for simultaneous joins.</p>
<div class="stats"><div class="stat"><strong>{self.db.total_joins()}</strong><br>Total joins</div><div class="stat"><strong>{len(invites)}</strong><br>Active invites</div></div>
<div class="exports"><a href="/exports/joins.csv">Joins CSV</a><a href="/exports/invites.csv">Invites CSV</a><a href="/exports/discord-invites.yml">Website mapping YAML</a></div>
<h2>Joins by source</h2><div class="table-wrap"><table><thead><tr><th>Source</th><th>Joins</th><th>Normal confidence</th><th>Latest</th></tr></thead><tbody>{source_rows}</tbody></table></div>
<h2>Recent joins</h2><div class="table-wrap"><table><thead><tr><th>Recorded</th><th>Member</th><th>Source</th><th>Invite</th><th>Confidence</th></tr></thead><tbody>{recent_rows}</tbody></table></div>
<h2>Active invites</h2><div class="table-wrap"><table><thead><tr><th>Source</th><th>Code</th><th>Type</th><th>Uses</th><th>Channel</th><th>Discord creator</th></tr></thead><tbody>{invite_rows}</tbody></table></div>
</main></body></html>"""
        return web.Response(text=body, content_type="text/html")

    async def joins_csv(self, request: web.Request) -> web.Response:
        payload = self.db.csv_export(self.db.recent_joins(100000))
        return _download(payload, "joins.csv", "text/csv")

    async def invites_csv(self, request: web.Request) -> web.Response:
        payload = self.db.csv_export(self.db.list_invites())
        return _download(payload, "invites.csv", "text/csv")

    async def website_yaml(self, request: web.Request) -> web.Response:
        return _download(
            render_website_mapping(self.db).encode("utf-8"),
            "discord-invites.yml",
            "application/yaml",
        )


def _download(payload: bytes, filename: str, content_type: str) -> web.Response:
    return web.Response(
        body=payload,
        content_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
