# BoostZapper Bot

The BoostZapper bot monitors Nostr events for replies that may contain key phrases, as well as direct messages from users.

When a user replies to a Nostr event that is actively being monitored, the bot reviews it to determine if the contents trigger an automatic reply message and/or zap to be sent to the user.  Only one zap per user, per event being monitored will be sent.

## Using the install script

For convenience, an installer script has been prepared that will create a dedicated boostzapper user, clone the repository, setup python environment with dependencies and install a service script.  

```sh
wget -qO- https://raw.githubusercontent.com/vicariousdrama/BoostZapper/main/botinstall.sh | sudo bash
```

If you use this script, you should change to the boostzapper user

```sh
sudo su boostzapper

cd /home/boostzapper/BoostZapper
```

... and then continue with the [Configuring the Server](#configuring-the-server) section.

## Clone the repository

To setup bot, you'll first need to clone the repository

```sh
git clone https://github.com/vicariousdrama/BoostZapper.git
```

## Preparation of Python Environment

To use this script, you'll need to run it with python 3.9 or higher and with the nostr, requests and bech32 packages installed.

First, create a virtual environment (or activate a common one)

```sh
python3 -m venv ~/.pyenv/boostzapper
source ~/.pyenv/boostzapper/bin/activate
```

Then install the dependencies
```sh
python3 -m pip install nostr@git+https://github.com/vicariousdrama/python-nostr.git
python3 -m pip install requests
python3 -m pip install bech32
python3 -m pip install boto3
```

## Configuring the Server

A subdirectory for storing `data` will be created if one does not exist on first run of the script.  Otherwise you can create and copy the sample configuration as follows:

```sh
mkdir -p data
cp -n sample-serverconfig.json data/serverconfig.json
```

Within this directory, a configuration file named `serverconfig.json` is read.  If this file does not exist, one will be created using the `sample-serverconfig.json`.

The server configuration file is divided into a few key sections. One for each of Nostr, Lightning Server, LN URL Providers, and Reports

### Nostr Config

Edit the configuration

```sh
nano data/serverconfig.json
```

The `nostr` configuration section has these keys

| key | description |
| --- | --- |
| botnsec | The nsec for the primary bot |
| botProfile | The metadata for the bot |
| relays | The list of relays the primary bot uses |
| operatornpub | The npub of the operator to relay support messages to |
| defaultProfile | The default profile fields for newly created zapper identities |
| fees | Fees the service should charge for types of processing, as measured in mcredits |
| excludeFromDirectMessages | Any npubs that direct messages should not be sent to. |

The most critical to define here is the `botnsec`.  You should generate an nsec on your own, and not use an existing one such as that for your personal usage.  For convenience, you can consider using the [vanitygen](vanitygen.md) script.

Within the `botProfile` are common metadata fields for the bot so that users of Nostr can learn more. You can set a friendly `name`, a brief `description`, urls for `picture` and `banner`, and optionally the `lud16` for lightning address, and `nip05`.  This information is checked and compared to the bots current profile on relays when started. If there is any changes, the bot will publish an updated profile automatically.

The `relays` section contains the list of relays that the bot will use to read events and direct messages, as well as publish profiles (kind 0 metadata), direct message responses (kind 4), replies (kind 1).  Each relay is configured with a url, and permissions for whether it can be read from or written to.

The `operatornpub` is a string that should contain the npub of the operator (thats you!) of the bot.  If a user messaging the bot wants to contact support, this is the npub that the messages are forwarded to.

The `defaultProfile` is structured similarly to the profile section. These values get assigned as defaults for newly created identities established from users using the bot to configure their own event to monitor and conditions.  Each user's bot identity is different to allow for tailoring the profile picture, banner, name etc associated with the bot. 

The `fees` section defines what the charges should be for different types of processing, as measured in mcredits (millicredits). A credit is equivalent to 1000 millicredits, and 1 credit is granted per satoshi.  At time of writing, there are 3 types of service fees:

- A `replyMessage` fee is charged each time a reply message is sent to a user reply that matched conditions on an event. 

- A `zapEvent` fee is charge for for each user reply that is zapped by the bot.

- The `time864` corresponds to the fee that is charged for each operational period of 864 seconds (1/100th or 1% of a day).

The `excludeFromDirectMessages` section denotes any npubs for which direct messages should be ignored, and for which no direct messages should be sent to.  For example, relay bots such as that from Nostr.wine

## Lightning Configuration

Edit the configuration

```sh
nano data/serverconfig.json
```

The `lnd` configuration section has these keys

| key | description |
| --- | --- |
| address | Where to reach the LND server |
| port | The listening port for LND server for GRPC REST calls |
| macaroon | The macaroon for authentication and authorization for the LND server in hex format |
| paymentTimeout | The time allowed in seconds to complete a payment or expire it |
| feeLimit | The maximum amount to allow for routing fees for each payment, in sats |
| connectTimeout | Time permitted in seconds to connect to LND |
| readTimeout | Time permitted in seconds to read all data from LND |
| activeServer | Optional name of a nested LND server configuration to use |
| servers | Optional object containing LND server configurations |

The `address` should be the ip address or fully qualified domain name to communicate with the LND server over REST

The `port` is the port the LND server is listening on for REST

The `macaroon` should be provided in hex format. 

The permissions needed are

- lnrpc.Lightning/DecodePayReq
- routerrpc.Router/SendPaymentV2
- routerrpc.Router/TrackPaymentV2
- lnrpc.Lightning/AddInvoice
- invoicesrpc.Invoices/LookupInvoiceV2

You can bake the macaroon as follows before convertng to hex.
```sh
lncli bakemacaroon uri:/lnrpc.Lightning/DecodePayReq uri:/routerrpc.Router/SendPaymentV2 uri:/routerrpc.Router/TrackPaymentV2 uri:/lnrpc.Lightning/AddInvoice uri:/invoicesrpc.Invoices/LookupInvoiceV2 --save_to ${HOME}/BoostZapper.macaroon

cat ${HOME}/BoostZapper.macaroon | xxd -p -c 1000
```

The `paymentTimeout` is the number of seconds that should be allowed for the payment to complete routing.  This helps avoid unnecessarily long in flights locking up funds.

The `feeLimit` is the maximum amount of fees, in sats, that you are willing to pay per zap performed, in addition to the amount being zapped.

The `connectTimeout` is the number of seconds to allow for making a connection to LND.

The `readTimeout` is the number of seconds to allow reading all data from LND.

The `activeServer` is an optional parameter whose value indicates the key name that should exist within the optional servers json object.

The `servers` field is an optional object that may contain nested LND server configurations that override the default values above when present and specified in the activeServer field.

The LND server needs to be reachable from where the script is run.

## LN Url Providers Configuration

Edit the configuration

```sh
nano data/serverconfig.json
```

The `lnurl` configuration section has these keys

| key | description |
| --- | --- |
| connectTimeout | Time permitted in seconds to connect to LN Url Providers |
| readTimeout | Time permitted in seconds to read all data from LN Url Providers |
| denyProviders | An optional list of domains hosting LN URL Providers that will not receive payouts |

The `connectTimeout` is the number of seconds to allow for making a connection to a LN Url Provider.

The `readTimeout` is the number of seconds to allow reading all data from a LN Url Provider.

The `denyProviders` is an array of strings containing entries of domain names for LN Url Providers that should not receive zaps even if they support it. This is helpful to exclude domains that are problematic with respect to HTLCs and may result in channel closures or loss of funds.

### Reports Configuration

Edit the configuration

```sh
nano data/serverconfig.json
```

The `reports` configuration section has a key for `aws` and nested within are

| key | description |
| --- | --- |
| enabled | Indicates whether s3 bucket upload is enabled |
| aws_access_key_id | AWS Access Key ID credential with write access to the s3 Bucket |
| aws_secret_access_key | AWS Secret Access Key credential with write access to the s3 Bucket |
| s3Bucket | The s3 bucket into which report files will be stored |
| baseKey | A folder path in the s3 bucket to use for the report files |
| pepper | A string, code, phrase etc to salt the npub before hashing to prevent users from finding other users reports |

## Running the Bot

Once configured, run the bot using the previously established virtual environment

```sh
~/.pyenv/boostzapper/bin/python bot.py
```

The console will show output reflecting each event being analyzed.

For further assistance or customizations, reach out to the developer on Nostr
- NIP05: vicariousdrama@nodeyez.com
- NPUB: npub1yx6pjypd4r7qh2gysjhvjd9l2km6hnm4amdnjyjw3467fy05rf0qfp7kza

Press `Control+C` to stop the bot process when satisfied its running properly.

If you used the installer script, a service was deployed named boostzapper-bot. This will be automatically run on startup, and can be started via

```sh
sudo systemctl start boostzapper-bot
```

