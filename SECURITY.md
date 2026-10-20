# Security

FactReel handles API keys and YouTube OAuth tokens. They are only read from environment variables / `.env`
and stored in your channel folder (`.factreel/youtube_token.json`); they are never sent anywhere except the
service they belong to.

If you find a vulnerability, please **don't open a public issue**: use
[GitHub private vulnerability reporting](https://github.com/DeadY2J/factreel/security/advisories/new). You'll get an answer within a few days.
