# BoostZapper

Boost Zapper is a service that monitors Nostr events, and can be configured to automatically zap responses and send reply messages based on characteristics of the original reply.

This project was prepared to support the #InkblotArt project by [Rex Damascus](https://nostr.band/npub12rzunrxvx89f78h4df284lzvkjqetljkq0200p62ygwmjevx0j8qhehrv9).  Programming by [Vicarious Drama](https://nostr.band/npub1yx6pjypd4r7qh2gysjhvjd9l2km6hnm4amdnjyjw3467fy05rf0qfp7kza)

---

## Supported NIPS

| NIP | Description |
| --- | --- |
| [NIP-01](https://github.com/nostr-protocol/nips/blob/master/01.md) | Basic Protocol Flow |
| [NIP-04](https://github.com/nostr-protocol/nips/blob/master/04.md) | Encrypted Direct Messages |
| [NIP-10](https://github.com/nostr-protocol/nips/blob/master/10.md) | Conventions for clients' use of e and p tags in text events |
| [NIP-19](https://github.com/nostr-protocol/nips/blob/master/19.md) | Bech-32 Encoded Entities |
| [NIP-21](https://github.com/nostr-protocol/nips/blob/master/21.md) | URI Scheme |
| [NIP-25](https://github.com/nostr-protocol/nips/blob/master/25.md) | Reactions |
| [NIP-42](https://github.com/nostr-protocol/nips/blob/master/42.md) | Client Authentication |
| [NIP-57](https://github.com/nostr-protocol/nips/blob/master/57.md) | Lightning Zaps |

---

## Supported Kinds

| Kind | Description |
| --- | --- |
| 0 | Metadata |
| 1 | Short Text Note |
| 4 | Encrypted Direct Messages |
| 7 | Reaction |
| 9734 | Zap Request |
| 22242 | Client Authentication |

---

## Boost Zapper Setup

### [Boost Zapper Bot](./docs/BotServer.md)
The primary bot logic that looks for events.  Start here if you want to set up the bot as an operator with an LND server.

### [Bot Commands](./docs/BotCommands.md)
For Users that want to configure the Zapper Bot for their own events and rules, this document provides the full list of commands. These commands are sent to Nostr users that direct message the bot for HELP.

---

## Helper Scripts

These scripts may be useful for those seeking smaller scripts to learn from.

### [One Off Script](./docs/BoostZapper.md)
The original Boost Zapper script proof of concept that runs a check for events and zaps based on conditions. Configuration differs slightly from that used for the Bot.  This is no longer supported and may not function any longer but is provided for posterity as a smaller subset of the current bot logic

### [Vanity Gen](./docs/vanitygen.md)
Simple script to calculate a vanity npub using the python-nostr library.  While functional, a more performant program would leverage multiple threads and likely be written in c, golang or rust

### [Sample Events](./docs/SampleEvents.md)
Simple script to dump some recent sample events by kind. This is very trivial mainly for diagnosis.

### [Sign and Send](./docs/SignAndSend.md)
Simple script that reads a json file, signs with the bot in server config, and sends to relays.

### [Calendar Maker](./docs/CalendarMaker.md)
A simple script that builds a calendar encompassing multiple events based on inputs