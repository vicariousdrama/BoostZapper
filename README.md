# BoostZapper

A simple script written in python that will look at responses or 
references users have made to a post identified by an event id 
(in hex or bech32 format), and if conditions are met, will attempt
to zap the user.

You can define conditions such as
- minimum length of a response
- inclusion of key phrases (e.g. including a hashtag or set of words)

Each condition set has an amount of sats that will be zapped if matched

Conditions are processed in order and the first match on a post
by a user determines the payment to be made.

A pubkey is only paid once per event being referenced, no matter how
many events they publish.  Likewise, a lightning address is only paid
once.  This is intended to reduce or at least somewhat thwart
automated responders.

## Preparation of Python Environment

To use this script, you'll need to run it with python 3.9 or higher
and with the nostr, requests and bech32 packages installed.

First, create a virtual environment (or activate a common one)

```sh
python3 -m venv ~/.pyenv/boostzapper
source ~/.pyenv/boostzapper/bin/activate
```

Then install the dependencies
```sh
python3 -m pip install nostr@git+https://github.com/callebtc/python-nostr.git
python3 -m pip install requests
python3 -m pip install bech32
```

## Configuration

A configuration file named `config.json` is required and takes the following form:

```json
{
    "botPrivateKey": "The hex or nsec of the bot. If not provided a new one is used for each run",
    "relays": [
        ""
    ],
    "referencedEventId": "The hex or bech32 representation of a nostr event id",
    "excludePubkeys": [
        ""
    ],
    "zapMessage": "Thanks for participating!",
    "zapConditions": [
        {
            "requiredPhrase": null,
            "requiredLength": 15,
            "zapAmount": 10
        }
    ],
    "lndServer": {
        "address": "127.0.0.1",
        "port": "10080",
        "macaroon": "020A3B6C....",
        "paymentTimeout": 30,
        "feeLimit": 5
    }
}
```

For convenience, you can start with the sample-config.json

```sh
cp sample-config.json config.json
```

The `botPrivateKey` should be configured to use the same identity
for the zap request events.  An event will get published to the
relays specified, so this key could be a personal one, or something
dedicated for this purpose. This value may be provided in hex or
as a nsec string.

The `relays` is an array of nostr relays that you want the
script to connect to fetch response events.  Don't include the
wss:// prefix.

The `referencedEventId` is used for specifying the event id. 
Ideally this should be the hex id of the nostr note, but many clients
only reveal the bech32 nevent string. To facilitate easy copy/pasta,
you can paste in event identifiers from clients and the script
will normalize as needed to hex format.

The `excludePubkeys` is as it implies, an array of values that
represent pubkeys of any publishers that should be excluded from
consideration for zapping.  These can be in hex or npub format.

The `zapMessage` field indicates a standardized message you want
to be included as a comment of the zap.

For `zapConditions`, this is an array of conditions processed
from the top down. The first set of conditions that matches an
event will be used for determining the amount to be zapped to
the user.  A zapCondition has the following form

```json
        {
            "requiredPhrase": null,
            "requiredLength": 15,
            "zapAmount": 10
        }
```

If `requiredPhrase` is specified as a string (not null), then
for this condition to match, the content the user published
must contain the phrase indicated. This check is case insensitive.
If the value is null, as indicated above, then a specific phrase
is not required to be zapped.

The `requiredLength` should be set to a number. The content that
a user posts must be at least this long in length for the condition
to match.

All required conditions must be met for the user to be zapped.

The `zapAmount` is the amount that will be zapped.

Only the first matching zapCondition will be applied to a user, so
put the most restrictive condition sets at the top of the array.

The `lndServer` is used for paying invoices to satisfy the zaps.
The configuration of such takes the following form

```json
    "lndServer": {
        "address.comment": "The IP address or FQDN to communicate with the LND server over REST",
        "address": "127.0.0.1",
        "port.comment": "The port the LND server is listening on for REST",
        "port": "10080",
        "macaroon.comment": "Macaroon for LND server in hex format.",
        "macaroon": "0201036C....",
        "paymentTimeout.comment": "Time permitted in seconds to complete a payment or expire it",
        "paymentTimeout": 30,
        "feeLimit.comment": "Fee limit, in sats, allowed for each payment made",
        "feeLimit": 5
    }
```

The `address` should be the ip address or fully qualified domain name
to communicate with the LND server over REST

The `port` is that port to connect to.

The `macaroon` should be provided in hex format. 

The permissions needed are

- lnrpc.Lightning/DecodePayReq
- routerrpc.Router/SendPaymentV2
- routerrpc.Router/TrackPaymentV2

You can bake the macaroon as follows before convertng to hex.
```sh
lncli bakemacaroon uri:/lnrpc.Lightning/DecodePayReq uri:/routerrpc.Router/SendPaymentV2 uri:/routerrpc.Router/TrackPaymentV2 --save_to ${HOME}/BoostZapper.macaroon

cat ${HOME}/BoostZapper.macaroon | xxd -p -c 1000
```

The `paymentTimeout` is the number of seconds that should be allowed
for the payment to complete routing.  This helps avoid unnecessarily
long in flights locking up funds.

The `feeLimit` is the maximum amount of fees, in sats, that you are
willing to pay per zap performed, in addition to the amount being
zapped.

The LND server needs to be reachable from where the script is run.

## Running

Once configured, to run the script simply execute the following
which will use the virtual python environment referenced.

change to the folder where boostzapper.py is

```sh
~/.pyenv/boostzapper/bin/python boostzapper.py
```

The console will show output reflecting each event being analyzed.

The following files will be created and updated

* **data/lightningIdcache.json** - This file contains a mapping of pubkeys to lightning addresses that is populated by pulling kind0 events for a pubkey.  Periodically this file may need to be deleted and rebuilt if users change their addresses

* **data/{eventid}.paid.json** - An output file that tracks the pubkeys that were zapped for the event referenced. This tracking prevents paying people twice. It also includes the amount paid, fees paid and other payment metadata

* **data/{eventid}.paidluds.json** - An output file that tracks the lightning addresses that were zapped for the event referenced. This tracking prevents paying people twice.

* **data/{eventid}.participants.json** - This file includes all pubkeys that created an event referring to the referenced event id, including those that were not zapped either for inelligibility due to the exclusion list, or not having a lightning address setup.