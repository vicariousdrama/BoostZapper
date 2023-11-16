# Sample Events

A simple script for retrieving events of a given kind from servers and dumping in json format.

This is primarily a diagnosis script to fetch events from the relays used by the bots.

Arguments can be provided to affect filtering. By default, this retrieves 20 text events made in the past day.  The following arguments are supported 

- --kind : return only those events of the given kind
- --author : filters to only events authored by the pubkey provided in hex format
- --since : filters to events published since the given timestamp
- --until : filters to events published no later than the given timestamp
- --limit : change how many events can be returned

Example run which returns up to 50 calendar date events published by Vic within a speific window of time from November 12 to November 14.

```sh
~/.pyenv/boostzapper/bin/python3 ./sampleevents.py --kind 31923 --since 1699810323 --until 1699983123 --limit 50 --author 21b419102da8fc0ba90484aec934bf55b7abcf75eedb39124e8d75e491f41a5e
```