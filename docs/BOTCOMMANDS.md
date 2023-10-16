# Bot Commands

Commands for interacting with the bot for purposes of configuring the bot, adding credits, and messaging support.

## HELP

The `HELP` command provides a summary of commands available

Example command:

```user
HELP
```

Example response:

```bot
HELP

FEES

RELAYS LIST

RELAYS ADD <relay>

RELAYS DELETE <index>

RELAYS CLEAR

CONDITIONS LIST

CONDITIONS ADD [--amount <zap amount if matched>] [--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>] [--requiredRegex <regular expression to match>] [--replyMessage <message to reply with if matched>]

CONDITIONS UP <index>

CONDITIONS DELETE <index>

CONDITIONS CLEAR

PROFILE [--name <name>] [--picture <url for profile picture>] [--banner <url for profile banner>] [--description <description of account>]

ZAPMESSAGE <message to send with zap>

EVENT <event identifier>

BALANCE

CREDITS ADD <amount>

ENABLE

DISABLE

STATUS

SUPPORT <message to send to support>
```

## FEES

The `FEES` command lists the current fee rates for the service

## RELAYS

The `RELAYS` command requires additional arguments to specify option and parameters

These relays are used for both retrieval of responses to an event, as well as inclusion in the zap request sent to LNURL Providers that support Nostr.

### RELAYS *`LIST`*

Reports the relays currently configured for the bot for you. By default, this will initialize with a set of relays associated with your pubkey.

Example command:

```user
RELAYS LIST
```

Example response:

```bot
Relays:
1) wss://nos.lol
2) wss://relay.nostr.bg
3) wss://relay.damus.io
4) wss://nostr.wine
5) wss://eden.nostr.land
```

The number listed in output may be used as the index to delete a relay as described below.

### RELAYS *`ADD`*

Use this command to add a relay to the list of those the bot should use.  

Required arguments:

- relay url

Example command:

```user
RELAYS ADD wss://e.nos.lol
```

Example response:

```bot
Relays:
1) wss://nos.lol
2) wss://relay.nostr.bg
3) wss://relay.damus.io
4) wss://nostr.wine
5) wss://eden.nostr.land
6) wss://e.nos.lol
```

### RELAYS *`DELETE`* &lt;index&gt;

Use this command to remove a relay from the list of those the bot should use, specifying the index of the relay as shown in the relay list.

Required arguments:

- index of relay to delete

Example command:
```user
RELAYS DELETE 2
```

Example response:
```bot
Relays:
1) wss://nos.lol
2) wss://relay.damus.io
3) wss://nostr.wine
4) wss://eden.nostr.land
5) wss://e.nos.lol
```

### RELAYS *`CLEAR`*

Use this command to remove all relays from the relay list. You will need to add relays again for the bot to operate.

Example command:
```user
RELAYS CLEAR
```

Example response:
```bot
Relays:

Relay list cleared.
```

## CONDITIONS

The `CONDITIONS` command requires additional arguments to specify option and parameters

These conditions are rulesets compared to a response someone makes to the referenced event.  If conditions match, then the publisher of the response will be zapped sats of the amount specified.  Conditions are compared in the order specified so more restrictive, or higher rewarding conditions should be specified first.

### CONDITIONS *`LIST`*

Reports the conditions currently configured for the bot for you. By default, this will initialize with a required length of 20, but no phrase required and a zap amount of 1.

Example command:

```user
CONDITIONS LIST
```

Example response:

```bot
Conditions:
1) zap 20 sats if length >= 20 and contains "#InkblotArt"
2) zap 10 sats if length >= 10
```

The number listed in output may be used as the index to delete a condition as described below.

### CONDITIONS *`ADD`*

Use this command to add a condition to the list of those the bot should use.  

Required arguments:

- --amount &lt;zapAmount&gt;

Optional arguments:

- --requiredPhrase &lt;phrase required&gt;
- --requiredLength &lt;length required&gt;

Example command:

```user
CONDITIONS ADD --amount 200 --requiredPhrase "#InkblotArt" --requiredLength 30
```

Example response:

```bot
Conditions:
1) zap 20 sats if length >= 20 and contains "#InkblotArt"
2) zap 10 sats if length >= 10
3) zap 200 sats if length >= 30 and contains "#InkblotArt"
```

### CONDITIONS *`UP`* &lt;index&gt;

Use this command to reorder conditions in the list, moving one at a time to a newer index.  This is helpful if you have defined conditions, but want to change the processing order

Required arguments:

- index of condition to promote

If the result of `CONDITIONS LIST` is as  follows:
```bot
Conditions:
1) zap 20 sats if length >= 20 and contains "#InkblotArt"
2) zap 10 sats if length >= 10
3) zap 200 sats if length >= 30 and contains "#InkblotArt"
```

Example command:
```user
CONDITIONS UP 3
```

Example response:
```bot
Conditions:
1) zap 20 sats if length >= 20 and contains "#InkblotArt"
2) zap 200 sats if length >= 30 and contains "#InkblotArt"
3) zap 10 sats if length >= 10
```

### CONDITIONS *`DELETE`* &lt;index&gt;

Use this command to remove a condition from the list of those the bot should use, specifying the index of the condition as shown in the conditions list.

Required arguments:

- index of condition to delete

Example command:
```user
CONDITIONS DELETE 2
```

Example response:
```bot
Conditions:
1) zap 20 sats if length >= 20 and contains "#InkblotArt"
2) zap 10 sats if length >= 10
```

### CONDITIONS *`CLEAR`*

Use this command to remove all conditions from the condition list. You will need to add conditions again for the bot to operate.

Example command:
```user
Conditions CLEAR
```

Example response:
```bot
Conditions:

Condition list cleared.
```

## PROFILE 

The `PROFILE` command allows for setting custom profile information for the bot that is zapping based on the conditions established.  Each account is assigned a unique bot identity and can be branded accordingly.  Likewise the npub of the bot can be used when registering for relay write access, archives, nip05 and other services.

Optional arguments:
- --name &lt;name&gt;
- --picture &lt;url for profile picture&gt;
- --banner &lt;url for profile banner&gt;
- --description &lt;description of account&gt;
- --lud16 &lt;lightning address&gt;
- --nip05 &lt;nostr address&gt;

Example command:
```user
PROFILE --name "Crabby Botzzapp"
```

```bot
Profile information

name: Crabby Botzzapp
description: This bot zaps participants of #InkblotArt by Rex Damascus
profile picture: https://nostrnodeyez.s3.amazonaws.com/inkblotart-crabby-botpfpt2.png
banner picture: none specified
lud16/lightning address: wearydoor58@walletofsatoshi.com
nip05/nostr address: crabby@nodeyez.com
```

## ZAPMESSAGE &lt;message to send with zap&gt;

When a nostr zap is sent, a message or comment can be included with the zap.  Different LNURL Providers can have their own constraints on whether messages are accepted, and of what length.  To avoid errors, its recommended to keep messages brief.  If your message contains a URL, some providers will turn that into a hyperlink, but may be limited to the first URL that appears within the message.

Example command:

```user
ZAPMESSAGE Thanks for sharing your interpretation of today's #InkblotArt!
```

Example response:

```bot
The zap message has been set to: Thanks for sharing your interpretation of today's #InkblotArt!
```

## EVENT &lt;eventid&gt;

The `EVENT` command requires specifying an event identifier to be monitored. Only one event can be monitored at a time per account.  The event identifier may be provided in bech32 or hexadecimal format.

Example command when providing bech32 format:
```user
EVENT nevent1qqsgq94vx9kq40zkyrr4e5lyw4knsqru779qexywkdglpsl8uwnrhhcpzemhxue69uhhyetvv9ujumn0wd68ytnzv9hxg9fx3dj
```

Example response:
```bot
Now monitoring event 8016ac..a63bdf
```

Example command when providing hex format:
```user
EVENT 8016ac316c0abc5620c75cd3e4756d38007cf78a0c988eb351f0c3e7e3a63bdf
```

Example response:
```bot
Now monitoring event 8016ac..a63bdf
```

Example command to set no event to be monitored:
```user
EVENT 0
```

Example response:
```bot
No longer monitoring an event
```

## BALANCE

The `BALANCE` command reports the balance of credits

Example command:

```user
BALANCE
```

Example response:

```bot
Your balance is 51223. To add credits, specify the full command. e.g. CREDITS ADD 21000
```

## CREDITS ADD &lt;amount&gt;

The `CREDITS` command allows for adding credits to the account for the bot to use for expenditures.  Credits are non-refundable and cover the cost of sending zaps and the routing fees required.

Required arguments:

- amount desired to be credited

Example command:

```user
CREDITS ADD 20000
```

Example response:

```bot
Please fulfill the following invoice to credit the account

lnbc200u1pjjg58cpp5g4uqmvplrf4k3unl6u24k2pr3eurzrxcl2zp7am24xtr6af3j68qhp5u9nxg2espa7m9wmhgm53um7f93z22ham5zgaymqccwhm2nuc3mhscqzzsxqyz5vqsp5rx73x3glr8jgzl5dewfthznggawnqjv6mnrklxsl5wxfyvkl6rjq9qyyssq69nucsuu6he7skk8a0354ddlp7hf348vadtnry9cyysh6qv60ye8r4kc7x0e7krf9qaexd9vxahqewc3mea26sc4kh7wmdw3lrsnfmsqdhw3pd
```

Your nostr client may turn the lightning invoice into a QR code or button for which to pay to complete the process.

When the bot recognizes the invoice as paid, a follow up message will be sent

```bot
Invoice paid. 20000 credits have been applied to your account
```

## STATUS

The `STATUS` command provides a simplified report of the configuration

Example command:
```user
STATUS
```

Example response:
```
The bot is configured with 5 relays, 2 conditions, and monitoring event 8016ac..a63bdf.

Responses to the event matching conditions will be zapped up to 20 sats with the following message: Thanks for sharing your interpretation of today's #InkblotArt!

   Credits applied: 200000
All time zaps sent:  78100
           Routing:    236
           Service:   6000
 Credits remaining: 115664
```

## ENABLE

The `ENABLE` command enables the bot to process messages and send zaps if the configuration is valid.  If there is a configuration requirement not met, the response will indicate as such

Example command:
```user
ENABLE
```

Example response:
```
Bot enabled!
```

Example response for a validation error
```
Unable to enable the bot. The eventId must be set. Use EVENT <event identifier>
```

## DISABLE

The `DISABLE` command disables the bot so that it will no longer continue processing events until started again.

Example command:
```user
DISABLE
```

Example response:
```
Bot disabled. Events will not be processed until re-enabled
```

## SUPPORT &lt;message to send to support&gt;

Under normal circumstances, the bot account itself is not monitored. Direct Encrypted messages with the bot allow for users to configure the bot and review status for their events without polluting the public feeds of nostr.

For convenience messages may be forwarded to the operator of the bot to draw attention to any issues that may be occurring or if you encounter a bug with the bot. 

Example command:

```user
SUPPORT I need additional rule types be added to the bot
```

Example response:

```bot
Your message has been forwarded through nostr relays. The operator may reach out to you directly or through other channels.  If you need to temporarily stop the bot, you can use the DISABLE command or set EVENT 0
```
