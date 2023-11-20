# Sample Events

A simple script for retrieving events of a given kind from servers and dumping in json format.

This is primarily a diagnosis script to fetch events from the relays used by the bots.

Arguments can be provided to affect filtering. By default, this retrieves 20 text events made in the past day.  The following arguments are supported 

- --kind : return only those events of the given kind
- --author : filters to only events authored by the pubkey provided in hex format
- --since : filters to events published since the given timestamp
- --until : filters to events published no later than the given timestamp
- --limit : change how many events can be returned
- --tag : filter by a tag

With exception to the --tag parameter, all arguments are expected to have a single value and not repeat. If the same argument is passed multiple times for kind, author, since, until, or limit, it overrides the previously provided value. Support for filtering events or multiple authors is not yet implemented.

The --tag parameter requires 2 values after it.  The first should be the single letter tag type. The next value should be the tag value to filter on.  Multiple --tags can be presented and it builds up a list to apply to the filter.

Example run which returns up to 50 calendar date events published by Vic within a speific window of time from November 12 to November 14.

```sh
~/.pyenv/boostzapper/bin/python3 ./sampleevents.py --kind 31923 --since 1699810323 --until 1699983123 --limit 50 --author 21b419102da8fc0ba90484aec934bf55b7abcf75eedb39124e8d75e491f41a5e
```

This example retrieves Community Definitions by a specific pubkey of the name 'Outdoors'
```sh
~/.pyenv/boostzapper/bin/python3 sampleevents.py --kind 34550 --author 026d8b7e7bcc2b417a84f10edb71b427fe76069905090b147b401a6cf60c3f27 --since 1680000000 --tag d Outdoors
```

Relatedly, this returns moderator approved events for the same community
```sh
~/.pyenv/boostzapper/bin/python3 sampleevents.py --kind 4550 --tag a 34550:026d8b7e7bcc2b417a84f10edb71b427fe76069905090b147b401a6cf60c3f27:Outdoors --since 1680000000
```