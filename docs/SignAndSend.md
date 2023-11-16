# Sample Events

Simple script that reads a json file, signs with the bot in server config, and sends to relays.

This is primarily a test script used to publish arbitrary events to relays that conform to NIP01.

When calling the script, a path to a JSON file should be provided.

The structure of the JSON file may include fields for

- content
- kind (required)
- tags

The created_at for an event will be assigned based on the current time.

The pubkey for the event will be taken from the bot's public key derived from private key defined in ./data/serverconfig.json

The event will be signed with the bot's private key defined in ./data/serverconfig.json

Example run

```sh
~/.pyenv/boostzapper/bin/python3 ./signandsend.py ~/path/to/sampleevent.json
```