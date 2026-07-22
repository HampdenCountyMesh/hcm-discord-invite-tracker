# HCM Discord Invite Tracker

A self-hosted Discord bot for Hampden County Mesh that records which public invite source most likely brought each new member into the server.

This repository is intentionally **HCM-first**. Its checked-in source catalog matches HCM's live website routes and its Docker deployment matches Meshcore-Hub. The code itself contains no HCM Discord IDs or tokens, so another community can fork the repository, replace the catalog and environment settings, and keep receiving upstream fixes.

## What it does

- Creates permanent, source-specific Discord invites.
- Attaches an existing invite to a source, including HCM's durable general link.
- Discovers invites made manually by Discord members.
- Infers the invite used when someone joins by comparing invite-use counters.
- Separates the Discord invite creator from the HCM administrator who created or attached a tracked source.
- Stores data in SQLite under `/meshdata`.
- Sends join-attribution logs to a private Discord channel.
- Provides an optional localhost dashboard and CSV exports.
- Generates a Jekyll `_data/discord_invites.yml` mapping for HCM's website.
- Makes daily SQLite backups and removes old member identifiers after a configurable retention period.

## Important limitation

Discord does not provide the used invite code in the member-join event. The bot compares invite-use counts immediately before and after a join. A single counter increase is normally reliable; simultaneous joins, outages, missing permissions, vanity links, and some deleted/expired invite situations can be ambiguous. Every row therefore includes a confidence value and reason.

## HCM architecture

```text
Discord member join
        │
        ▼
HCM Invite Tracker container
        ├── SQLite: /meshdata/hcm-invite-tracker/invite-tracker.sqlite3
        ├── backups: /meshdata/hcm-invite-tracker/backups/
        ├── website export: /meshdata/hcm-invite-tracker/discord-invites.yml
        ├── private Discord join log
        └── localhost dashboard: 127.0.0.1:8091
```

The bot does **not** hold a GitHub token. The generated website mapping is reviewed and committed separately, so compromise of the Discord bot does not grant write access to `hampdencountymesh.org`.

## Discord application setup

1. Create an application and bot in the Discord Developer Portal.
2. Under **Privileged Gateway Intents**, enable **Server Members Intent**. Message Content Intent is not needed.
3. Install the app into the HCM server with the `bot` and `applications.commands` scopes.
4. Grant only the permissions the tracker needs:
   - View Channels
   - Send Messages
   - Embed Links
   - Attach Files
   - Create Instant Invite
   - Manage Server

`Manage Server` is required because Discord only includes invite-use metadata when the bot retrieves the server's invites with that permission. `Create Instant Invite` is required for `/source provision` and `/source provision-all`.

Create or choose:

- A private staff channel for join-attribution logs.
- A public welcome or lobby channel that new source invites should open.
- Optionally, an HCM admin or Infra Ops role allowed to run tracker commands.

Enable Discord Developer Mode, then copy the server, channel, and optional role IDs.

## Install on Meshcore-Hub

Clone or copy the repository onto the hub, then:

```bash
cd hcm-discord-invite-tracker
./scripts/install-hcm.sh
```

The first run creates `.env` and stops. Edit it:

```bash
nano .env
```

Fill in at least:

```dotenv
DISCORD_TOKEN=...
GUILD_ID=...
LOG_CHANNEL_ID=...
DEFAULT_INVITE_CHANNEL_ID=...
```

Then run the installer again:

```bash
./scripts/install-hcm.sh
```

Check it with:

```bash
./scripts/check-hcm.sh
```

The compose file:

- Uses `/meshdata/hcm-invite-tracker` for persistent data.
- Binds the dashboard only to `127.0.0.1:8091`.
- Drops Linux capabilities and uses a read-only container filesystem.
- Limits container memory to 256 MB.
- Rotates Docker logs.

## First HCM provisioning

The checked-in catalog contains the live HCM routes:

```text
general
site-nav
home-bottom
getting-started
guides
better-coverage
updates
flier
card
404
```

The `general` source contains HCM's existing durable invite as a preferred code. At startup, the bot will attach it automatically when that invite is still active and visible.

In Discord, run:

```text
/source list
/source refresh
```

Then create the remaining permanent links:

```text
/source provision-all confirm:CREATE
```

Or create them one at a time:

```text
/source provision source:site-nav
```

To attach a pre-existing invite manually:

```text
/source attach source:general invite:https://discord.gg/egyUeREcmX
```

Other useful commands:

```text
/source export
/report summary
/report recent
```

All command responses are ephemeral. Commands are available to members with Manage Server, Administrator, or a role listed in `ADMIN_ROLE_IDS`.

## Controlled test

Use one source link in a private browser or a test Discord account that is not already in the server. After joining, verify:

1. The private log names the expected source and code.
2. Confidence is `normal`.
3. `/report recent` shows the join.
4. The dashboard health endpoint responds:

```bash
curl http://127.0.0.1:8091/healthz
```

Do not test by clicking an invite with an account already in the server; that does not produce a member-join event.

## Website integration

The current HCM website already uses `join_source` on each `/join/.../` redirect page. The bot writes:

```text
/meshdata/hcm-invite-tracker/discord-invites.yml
```

Copy it into the website repository as:

```text
_data/discord_invites.yml
```

Then apply the small Liquid lookup described in [`website/README.md`](website/README.md). The existing `_config.yml` invite remains the fallback if a source has not yet been provisioned.

This is deliberately a review-and-commit step. Automatic website pushes can be added later through a narrowly scoped deployment workflow, but putting a GitHub write token in the Discord bot container is not recommended.

## Dashboard access

The dashboard is available locally at:

```text
http://127.0.0.1:8091/
```

From another computer, use an SSH tunnel rather than exposing it publicly:

```bash
ssh -L 8091:127.0.0.1:8091 newports@Meshcore-Hub
```

Then open `http://127.0.0.1:8091/` on that computer.

The dashboard can also enforce Basic authentication with `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD`. Do not publish it through Caddy without authentication and HTTPS; it contains member and invite information.

## Data and privacy

By default, member IDs, names, and account creation dates are purged from join rows after 90 days. Source attribution, confidence, timestamp, and aggregate counts remain. Change `IDENTITY_RETENTION_DAYS` in `.env`; `0` disables automatic purging.

Backups are created daily with SQLite's online backup API. The newest 14 are retained by default. Tokens and dashboard passwords belong only in `.env`, which is ignored by Git.

## How another community uses this

They click **Fork** on GitHub. A fork is their own connected copy of this repository. They then:

1. Replace `config/hcm-sources.yml` with their project name and source routes.
2. Copy `.env.hcm.example` to `.env` and use their Discord IDs.
3. Adjust the persistent-data path and port in the compose file if needed.
4. Keep their server-specific changes in their fork.
5. Submit generally useful bug fixes back to HCM through a pull request.

HCM remains the upstream working version. There is no second “generic branch” to maintain, and bug fixes do not need to be copied manually between two codebases.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

The GitHub Actions workflow runs linting, tests, bytecode compilation, and a Docker build.

## License

MIT. See [`LICENSE`](LICENSE).
