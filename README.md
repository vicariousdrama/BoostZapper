# BoostZapper

Boost Zapper is a service that monitors events on Nostr, and can be configured to automatically zap responses or send reply messages based on characteristics of the original reply.

This project was prepared to support the #InkblotArt project by [Rex Damascus](https://nostr.band/npub12rzunrxvx89f78h4df284lzvkjqetljkq0200p62ygwmjevx0j8qhehrv9).  Programming by [Vicarious Drama](https://nostr.band/npub1yx6pjypd4r7qh2gysjhvjd9l2km6hnm4amdnjyjw3467fy05rf0qfp7kza)

---

## [Boost Zapper Bot](./docs/BotServer.md)
The primary bot logic that looks for events.  Start here if you want to set up the bot as an operator with an LND server.

## [Bot Commands](./docs/BotCommands.md)
For Users that want to configure the Zapper Bot for their own events and rules, this document provides the full list of commands.

## [One Off Script](./docs/BoostZapper.md)
The original Boost Zapper script proof of concept that runs a check for events and zaps based on conditions. Configuration differs slightly from that used for the Bot.

## [Vanity Gen](./docs/vanitygen.md)
Simple script to calculate a vanity npub