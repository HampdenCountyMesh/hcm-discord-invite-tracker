# Security

Do not commit Discord bot tokens, dashboard passwords, production SQLite databases, or raw join exports.

The HCM compose file binds the dashboard to `127.0.0.1`. Keep it local unless it is placed behind authentication and HTTPS. The bot deliberately has no GitHub credential and cannot modify the public website.

To report a vulnerability privately, use HCM's published security contact rather than a public issue when disclosure would expose a token, member data, or an active exploit.
