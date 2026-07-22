# HCM website integration

The bot writes `/data/discord-invites.yml`. Copy that file into the website repository as:

```text
_data/discord_invites.yml
```

Then apply `hcm-website.patch`, or replace the first two assignment lines in `_layouts/join-redirect.html` with the contents of `join-redirect-data-snippet.liquid`.

The resulting lookup order is:

1. A page-specific `discord_invite_url`, if deliberately set.
2. The source URL in `_data/discord_invites.yml`.
3. The site-wide `discord_invite_url` in `_config.yml`.
4. The durable HCM general invite fallback.

The bot does not receive a GitHub token and does not push to the website. This is intentional: compromise of the Discord bot should not grant write access to the public site. Review and commit the generated mapping through the normal website workflow.
