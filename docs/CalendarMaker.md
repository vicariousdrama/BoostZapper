# Calendar Maker

This is a utility script to build and publish a calendar based on configuration.

It expects the serverconfig.json file in the data folder as configured for the bot, as well as a calendarconfig.json file structured as follows

```json
{
    "frequency": 14400,
    "searchlist": [
      {"kind": 31924, "author": "90cca4db5ad5a9359d88ed8a6710df461d73a7e51b02e633016aefc05b130ac6", "d": "a3e6a7c8"},
      {"kind": 31923, "author": "21b419102da8fc0ba90484aec934bf55b7abcf75eedb39124e8d75e491f41a5e", "phrase": "bitcoin"},
      {"kind": 31923, "author": "1eb5d2c90ae0b1c07105d29c3861f5c36c0245aee8b09196339e6c25ee9e8d5f", "phrase": "bitcoin"},
      {"kind": 31923, "author": "a136247d8caf7e30bf403d32006faeca0c9d1cec7a16075e4142c2fed6cade60", "phrase": "bitcoin"}
    ],
    "name": "Mid-Atlantic Bitcoin Events",
    "content": "Covering DC, DE, MD, NJ, PA, VA, WV. Rollup of events found individually and in calendars from the region for Bitcoin",
    "description": "A collection of Bitcoin events taking place in the Mid-Atlantic area of the United States. For purposes of this calendar, this encompasses the following states: Delaware, New Jersey, Maryland, Pennsylvania, Virginia, West Virginia, and the District of Columbia",
    "uuid": "5fdcaa30-77b7-4607-b7f7-9a9a62e01a5b",
    "image": "https://nostrnodeyez.s3.amazonaws.com/calendars/midatlantic-bitcoin-calendar2.png"
}
```

The `frequency` field is how often the calendar should be rebuilt when run as a background process.  Setting this value to 0 will run once and exit.

The `searchlist` is an array. The kind value for each item can be either another calendar (31924), for which all events will be added, or date (31922) or time (31923) events published by the referenced author.  The phrase will be compared in a case insensitive way to any returned events against the event content, or tags for the name or description.

The `name` field is the name for the calendar

The `content` field is what is used by Flockstr.com for the short description.

The `description` field may be superfluous. Flockstr creates for its calendars but doesnt seem to use, and is nonstandard and otherwise a duplicate of the content.

The `uuid` should be a universally unique identifier per calendar. This is assumed to be unique per pubkey for indexing, but not verified. Flockstr uses short 8 character hexadecimal (4 byte) values.

The `image` is used as the calendar image and banner. Flockstr supports multiple images. The ratio for images for banner format is 10:4 or else it will be truncated.  

Example run

```sh
~/.pyenv/boostzapper/bin/python3 ./calendarmaker.py
```