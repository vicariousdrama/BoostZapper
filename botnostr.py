#!/usr/bin/env python3
from datetime import datetime, timedelta
from urllib3.exceptions import InsecureRequestWarning, ReadTimeoutError
from nostr.key import PrivateKey, PublicKey
from nostr.event import Event, EventKind, EncryptedDirectMessage
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
from nostr.relay_manager import RelayManager
import bech32
import json
import ssl
import time
import botfiles as files
import botutils as utils
import botledger as ledger
import botlnd as lnd

logger = None
config = None
handledMessages = {}

def getNpubConfigFilename(npub):
    return f"{files.dataFolder}users/{npub}.json"

def getNpubConfigFile(npub):
    filename = getNpubConfigFilename(npub)
    npubConfig = files.loadJsonFile(filename)
    if npubConfig is None: return {}
    return npubConfig

def getBotPrivateKey():
    if "botnsec" not in config: 
        logger.warning("Server config missing 'botnsec' in nostr section.")
        return None
    botNsec = config["botnsec"]
    botPrivkey = PrivateKey().from_nsec(botNsec)
    return botPrivkey

def getBotPubkey():
    botPrivkey = getBotPrivateKey()
    if botPrivkey is None: return None
    return botPrivkey.public_key.hex

def getOperatorNpub():
    if "operatornpub" not in config:
        logger.warning("Server config missing 'operatornpub' in nostr section.")
        return None
    operatornpub = config["operatornpub"]
    return operatornpub

def sendDirectMessage(npub, message):
    if npub is None:
        logger.warning("Unable to send direct message to recipient npub (value is None)")
        logger.warning(f" - message: {message}")
        return
    botPubkey = getBotPubkey()
    if botPubkey is None:
        logger.warning("Unable to send direct message to npub")
        logger.warning(f" - npub: {npub}")
        logger.warning(f" - message: {message}")
        return
    recipient_pubkey = PublicKey().from_npub(npub).hex
    dm = EncryptedDirectMessage(
        recipient_pubkey=recipient_pubkey,
        cleartext_content=message
    )
    getBotPrivateKey().sign_event(dm)
    relay_manager = RelayManager()
    relays = getNostrRelaysFromConfig(config)
    for nostrRelay in relays:
        relay_manager.add_relay(nostrRelay)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    time.sleep(1.25) # allow the connections to open
    relay_manager.publish_event(dm)
    relay_manager.close_connections()

def checkDirectMessages():
    global handledMessages          # tracked in this file, and only this function
    botPubkey = getBotPubkey()
    if botPubkey is None:
        logger.warning("Unable to check direct messages")
        return
    newMessages = []
    t=int(time.time())
    since = t - 300 # 5 minutes ago
    # remove older from handled
    for k, v in handledMessages.items():
        if v < since:
            del handledMessages[k]
    # setup filter to retrieve direct messages sent to us
    filters = Filters([Filter(
        since=since,
        pubkey_refs=botPubkey,
        kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE]
        )])
    subscription_id = f"inbox-{since}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    # connect to relays
    relay_manager = RelayManager()
    relays = getNostrRelaysFromConfig(config)
    for nostrRelay in relays:
        relay_manager.add_relay(nostrRelay)
    relay_manager.add_subscription(subscription_id, filters)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    time.sleep(1.25) # allow the connections to open
    # push request to relays
    message = json.dumps(request)
    relay_manager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # wait for events to return, gather and close
    while relay_manager.message_pool.has_events():
        event_msg = relay_manager.message_pool.get_event()
        # only add those not already in the handledMessages list
        if event_msg.event.id not in handledMessages:
            newMessages.append(event_msg)
            handledMessages[event_msg.event.id, event_msg.event.created_at]
    relay_manager.close_subscription(subscription_id)
    relay_manager.close_connections()
    return newMessages

def isValidSignature(event): 
    sig = event.signature
    id = event.id
    publisherPubkey = event.public_key
    pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey))
    return pubkey.verify_signed_message_hash(hash=id, sig=sig)

def processDirectMessages(messages):
    for message in messages:
        if not isValidSignature(message.event): continue
        publisherHex = str(message.event.public_key).strip()
        publisherPubkey = PublicKey(raw_bytes=bytes.fromhex(publisherHex)).bech32
        content = str(message.event.content).strip()
        firstWord = content.split()[0].upper()
        if firstWord == "HELP":
            handleHelp(publisherPubkey, content)
        elif firstWord == "RELAYS":
            handleRelays(publisherPubkey, content)
        elif firstWord == "CONDITIONS":
            handleConditions(publisherPubkey, content)
        elif firstWord == "PROFILE":
            handleProfile(publisherPubkey, content)
        elif firstWord == "ZAPMESSAGE":
            handleZapMessage(publisherPubkey, content)
        elif firstWord == "EVENT":
            handleEvent(publisherPubkey, content)
        elif firstWord == "CREDITS":
            handleCredits(publisherPubkey, content)
        elif firstWord == "STATUS":
            handleStatus(publisherPubkey, content)
        elif firstWord == "SUPPORT":
            handleSupport(publisherPubkey, content)
        else:
            handleHelp(publisherPubkey, content)

def handleHelp(npub, content):
    words = content.split()
    handled = False
    message = ""
    if len(words) > 2:
        secondWord = str(words[1]).upper()
        if secondWord == "RELAYS":
            message = "Relays commands:"
            message = f"{message}\nRELAYS LIST"
            message = f"{message}\nRELAYS ADD <relay>"
            message = f"{message}\nRELAYS DELETE <index>"
            message = f"{message}\nRELAYS CLEAR"
            handled = True
        elif secondWord == "CONDITIONS":
            message = "Conditions commands:\nCONDITIONS LIST"
            message = f"{message}\nCONDITIONS ADD [--amount <zap amount if matched>][--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>]"
            message = f"{message}\nCONDITIONS UP <index>"
            message = f"{message}\nCONDITIONS DELETE <index>"
            message = f"{message}\nCONDITIONS CLEAR"
            handled = True
        elif secondWord == "PROFILE":
            message = "Profile commands:"
            message = f"{message}\nPROFILE [--name <name>] [--picture <url for profile picture>] [--banner <url for profile banner>] [--description <description of account>]"
            handled = True
        elif secondWord == "ZAPMESSAGE":
            message = "Zap Message commands:"
            message = f"{message}\nZAPMESSAGE <message to send with zap>"
            handled = True
        elif secondWord == "EVENT":
            message = "Event commands:"
            message = f"{message}\nEVENT <event identifier>"
            handled = True
        elif secondWord == "CREDITS":
            message = "Credits commands:"
            message = f"{message}\nCREDITS ADD <amount>"
            handled = True
        elif secondWord == "STATUS":
            message = "Reports the current summary status for your bot account"
            handled = True
        elif secondWord == "SUPPORT":
            message = "Attempts to forward a message to the operator of the service"
            message = f"{message}\nSUPPORT <message to send to support>"
            handled = True
    if not handled:
        message = "This bot can zap responses to an event you set with conditions. To get detailed help, issue the subcommand after the HELP option (e.g. HELP RELAYS)"
        message = f"{message}\nCommands: RELAYS CONDITIONS PROFILE ZAPMESSAGE EVENT CREDITS STATUS SUPPORT"
    sendDirectMessage(npub, message)

def getNostrFieldForNpub(npub, fieldname):
    npubConfig = getNpubConfigFile(npub)
    if fieldname in npubConfig:
        return npubConfig[fieldname]
    else:
        return ""

def setNostrFieldForNpub(npub, fieldname, fieldvalue):
    npubConfig = getNpubConfigFile(npub)
    if fieldvalue is not None:
        npubConfig[fieldname] = fieldvalue
    else:
        del npubConfig[fieldname]
    filename = getNpubConfigFilename(npub)
    files.saveJsonFile(filename, npubConfig)

def getNostrRelaysForNpub(npub):
    npubConfig = getNpubConfigFile(npub)
    return getNostrRelaysFromConfig(npubConfig)

def getNostrRelaysFromConfig(aConfig):
    relays = []
    if "relays" in aConfig:
        for relay in aConfig["relays"]:
            if str(relay).startswith("wss://"):
                relays.append(relay)
            else:
                relays.append(f"wss://{relay}")
    return relays

def handleRelays(npub, content):
    npubRelays = getNostrRelaysForNpub(npub)
    words = content.split()
    if len(words) > 1:
        secondWord = str(words[1]).upper()
        if secondWord == "CLEAR":
            npubRelays = []
            setNostrFieldForNpub(npub, "relays", npubRelays)
        if secondWord == "ADD":
            if len(words) > 2:
                newRelay = words[2]
                npubRelays.append(newRelay)
                setNostrFieldForNpub(npub, "relays", npubRelays)
            else:
                sendDirectMessage(npub, "Please provide the relay to be added\nRELAYS ADD wss://relay.example.com")
                return
        if secondWord == "DELETE":
            if len(words) <= 2:
                sendDirectMessage(npub, "Please provide the index of the relay to be deleted\nRELAYS DELETE 3")
                return
            value2Delete = words[2]
            if str(value2Delete).isdigit():
                idxNum = int(value2Delete)
                if idxNum <= 0:
                    sendDirectMessage(npub, "Please provide the index of the relay to be deleted\nRELAYS DELETE 3")
                    return
                if idxNum > len(npubRelays):
                    sendDirectMessage(npub, "Index not found in relay list")
                else:
                    idxNum -= 1 # 0 based
                    del npubRelays[idxNum]
                    setNostrFieldForNpub(npub, "relays", npubRelays)
            else:
                if value2Delete in npubRelays:
                    npubRelays.remove(value2Delete)
                    setNostrFieldForNpub(npub, "relays", npubRelays)
                else:
                    sendDirectMessage(npub, "Item not found in relay list")
    # If still here, send the relay list
    idx = 0
    message = "Relays:"
    if len(npubRelays) > 0:
        for relay in npubRelays:
            idx += 1
            message = f"{message}\n{idx}) {relay}"
    else:
        message = f"{message}\n\nRelay list is empty"
    sendDirectMessage(npub, message)

def getNostrConditionsForNpub(npub):
    npubConfig = getNpubConfigFile(npub)
    if "conditions" in npubConfig:
        return npubConfig["conditions"]
    else:
        return []

def handleConditions(npub, content):
    conditions = getNostrConditionsForNpub(npub)
    words = content.split()
    if len(words) > 1:
        secondWord = str(words[1]).upper()
        if secondWord == "CLEAR":
            conditions = []
            setNostrFieldForNpub(npub, "conditions", conditions)
        if secondWord == "ADD":
            if len(words) > 2:
                commandWord = None
                newCondition = {
                    "amount":0, 
                    "requiredLength":0,
                    "requiredPhrase":None
                    }
                for word in words[2:]:
                    if word in ("--amount", "--requiredLength", "--requiredPhrase"):
                        if commandWord is None:
                            commandWord = word
                            combinedWords = ""
                        else:
                            if commandWord == "--amount":
                                if str(combinedWords).isdigit():
                                    newCondition["amount"] = int(combinedWords)
                                commandWord = word
                            if commandWord == "--requiredLength":
                                if str(combinedWords).isdigit():
                                    newCondition["requiredLength"] = int(combinedWords)
                                commandWord = word
                            if commandWord == "--requiredPhrase":
                                newCondition["requiredPhrase"] = combinedWords
                                commandWord = word
                    else:
                        combinedWords = "{combinedWords} {word}" if len(combinedWords) > 0 else word
                if commandWord is not None:
                    if commandWord == "--amount":
                        if str(combinedWords).isdigit():
                            newCondition["amount"] = int(combinedWords)
                    if commandWord == "--requiredLength":
                        if str(combinedWords).isdigit():
                            newCondition["requiredLength"] = int(combinedWords)
                    if commandWord == "--requiredPhrase":
                        newCondition["requiredPhrase"] = combinedWords
                # validate before adding
                if newCondition["amount"] == 0:
                    sendDirectMessage(npub, "Amount for new condition must be greater than 0")
                    return
                conditions.append(newCondition)
                setNostrFieldForNpub(npub, "conditions", conditions)
            else:
                sendDirectMessage(npub, "Please provide the condition to be added\nCONDITIONS ADD [--amount <zap amount if matched>][--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>]")
                return
        if secondWord == "UP":
            if len(words) <= 2:
                sendDirectMessage(npub, "Please provide the index of the condition to move up\nCONDITIONS UP 3")
                return
            value2Move = words[2]
            if str(value2Move).isdigit():
                idxNum = int(value2Move)
                if idxNum <= 0:
                    sendDirectMessage(npub, "Please provide the index of the condition to be move up\nCONDITIONS UP 3")
                    return
                if idxNum > len(conditions):
                    sendDirectMessage(npub, "Index not found in condition list")
                else:
                    idxNum -= 1 # 0 based
                    del conditions[idxNum]
                    setNostrFieldForNpub(npub, "conditions", conditions)
            else:
                sendDirectMessage(npub, "Please provide the index of the condition to be move up as a number\nCONDITIONS UP 3")
                return
        if secondWord == "DELETE":
            if len(words) <= 2:
                sendDirectMessage(npub, "Please provide the index of the condition to be deleted\nCONDITION DELETE 3")
                return
            value2Delete = words[2]
            if str(value2Delete).isdigit():
                idxNum = int(value2Delete)
                if idxNum <= 0:
                    sendDirectMessage(npub, "Please provide the index of the condition to be deleted\nCONDITIONS DELETE 3")
                    return
                if idxNum > len(conditions):
                    sendDirectMessage(npub, "Index not found in conditions list")
                else:
                    idxNum -= 1 # 0 based
                    del conditions[idxNum]
                    setNostrFieldForNpub(npub, "conditions", conditions)
            else:
                sendDirectMessage(npub, "Please provide the index of the condition to be deleted as a number\nCONDITIONS DELETE 3")
                return
    # If still here, send the condition list
    idx = 0
    message = "Conditions:"
    if len(conditions) > 0:
        for condition in conditions:
            idx += 1
            conditionAmount = condition["amount"]
            message = f"{message}\n{idx}) zap {conditionAmount} sats"
            rCount = 0
            if "requiredLength" in condition:
                conditionRequiredLength = condition["requiredLength"]
                if conditionRequiredLength is not None and conditionRequiredLength > 0:
                    message = f"{message} if" if rCount == 0 else f"{message} and"
                    message = f"{message} length >= {conditionRequiredLength}"
                    rCount += 1
            if "requiredPhrase" in condition:
                conditionRequiredPhrase = condition["requiredPhrase"]
                if conditionRequiredPhrase is not None and len(conditionRequiredPhrase) > 0:
                    message = f"{message} if" if rCount == 0 else f"{message} and"
                    message = f"{message} contains {conditionRequiredPhrase}"
                    rCount += 1
    else:
        message = f"{message}\n\nCondition list is empty"
    sendDirectMessage(npub, message)

def getNostrProfileForNpub(npub):
    # this is the bot profile from config, not from kind0
    npubConfig = getNpubConfigFile(npub)
    if "profile" in npubConfig:
        return npubConfig["profile"]
    else:
        newPrivateKey = PrivateKey()
        newProfile = {
            "name": "bot",
            "nsec": newPrivateKey.bech32,
            "npub": newPrivateKey.public_key.bech32,
            "nip05": "",
            "lud16": "",
            "picture": "",
            "banner": "",
            "description": ""
        }
        setNostrFieldForNpub(npub, "profile", newProfile)
        return newProfile

def handleProfile(npub, content):
    hasChanges = False
    profile = getNostrProfileForNpub(npub)
    words = content.split()
    if len(words) > 1:
        commandWord = None
        for word in words[1:]:
            if str(word).startswith("--"):
                if commandWord is None:
                    commandWord = word[2:]
                    combinedWords = ""
                else:
                    if commandWord in ("name","description","nip05","lud16","picture","banner"):
                        if profile[commandWord] != combinedWords:
                            hasChanges = True
                        profile[commandWord] = combinedWords
                    commandWord = word
            else:
                combinedWords = "{combinedWords} {word}" if len(combinedWords) > 0 else word                
        if commandWord is not None:
            if profile[commandWord] != combinedWords:
                hasChanges = True
            profile[commandWord] = combinedWords
        if hasChanges:
            setNostrFieldForNpub(npub, "profile", profile)
            publishProfile(npub)
    else:
        sendDirectMessage(npub, "Please provide the fields to set in the profile\ne.g. PROFILE --name Bob the Bot --picture https://some.nostr.site/image.png --banner https://nostr.site/banner.png --description This is a cool bot")
        return
    # Report fields in profile (except nsec)
    message = "Profile information:\n"
    for k, v in profile.items():
        if k not in ("nsec"):
            message = f"{message}\n{k}: {v}"
    sendDirectMessage(npub, message)

def publishProfile(npub):
    profile = getNostrProfileForNpub(npub)
    j = {}
    kset = ("name","description","nip05","lud16","picture","banner")
    for k in kset: 
        if k in profile and len(profile[k]) > 0: j[k] = profile[k]
    content = json.dumps(j)
    publickeyhex = utils.bech32ToHex(npub)
    kind0 = Event(
        content=content,
        public_key=publickeyhex,
        kind=EventKind.SET_METADATA,
        )
    profileNsec = profile["nsec"]
    profilePK = PrivateKey().from_nsec(profileNsec)
    profilePK.sign_event(kind0)
    relay_manager = RelayManager()
    relays = getNostrRelaysForNpub(npub)
    for nostrRelay in relays:
        relay_manager.add_relay(nostrRelay)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    time.sleep(1.25) # allow the connections to open
    relay_manager.publish_event(kind0)
    relay_manager.close_connections()

def handleZapMessage(npub, content):
    zapMessage = getNostrFieldForNpub(npub, "zapMessage")
    words = content.split()
    if len(words) > 1:
        zapMessage = " ".join(words[1:])
        setNostrFieldForNpub(npub, "zapMessage", zapMessage)
    message = f"The zap message is set to: {zapMessage}"
    sendDirectMessage(npub, message)

def handleEvent(npub, content):
    eventId = getNostrFieldForNpub(npub, "eventId")
    words = content.split()
    if len(words) > 1:
        eventId = words[1]
        if eventId == "0": eventId = ""
        if str(eventId).startswith("nostr:"): eventId = eventId[6:]
        if "note1" or "nevent" in eventId:
            eventId = utils.bech32ToHex(eventId)
            if eventId == "":
                sendDirectMessage(npub, "Event id could not be decoded from bech32 string")
                return
        if len(eventId) > 0:
            if not (utils.isHex(eventId) and len(eventId) == 64):
                sendDirectMessage(npub, "Event id should be 64 characters when provided as hex")
                return
        setNostrFieldForNpub(npub, "eventId", eventId)
    if eventId is None or len(eventId) == 0:
        message = "No longer monitoring an event"
    else:
        eventIdhex = eventId
        eventIdbech32 = utils.hexToBech32(eventId, "nevent")
        shorthex = eventIdhex[0:6] + ".." + eventIdhex[-6:]
        shortbech32 = eventIdbech32[0:12] + ".." + eventIdbech32[-6:]
        message = "Now monitoring event"
        message = f"{message}\n  hex: {shorthex}"
        message = f"{message}\n  hex: {shortbech32}"
    sendDirectMessage(npub, message)

def handleCredits(npub, content):
    # See if there is an existing unexpired invoice
    currentInvoice = getNostrFieldForNpub(npub, "currentInvoice")
    if type(currentInvoice) is dict:
        current_time, _ = utils.getTimes()
        if current_time > currentInvoice["expiry_time"]:
            # remove current invoice and create fresh
            currentInvoice = {}
            setNostrFieldForNpub(npub, "currentInvoice", currentInvoice)
        else:
            # existing invoice is still valid, dont create a new one
            expiry_time_iso = currentInvoice["expiry_time_iso"]
            payment_request = currentInvoice["payment_request"]
            message = "An existing invoice has not yet been paid or expired"
            message = f"{message}\nThis invoice expires {expiry_time_iso}"
            message = f"{message}\n{payment_request}"
            sendDirectMessage(npub, message)
            return
    else:
        currentInvoice = {}
    words = content.split()
    amount = 0
    if len(words) > 2:
        firstWord = words[1]
        secondWord = words[2]
        if str(firstWord).upper() == "ADD" and str(secondWord).isdigit():
            amount = int(secondWord)
    if amount == 0:
        sendDirectMessage(npub, "To add credits, specify the full command. e.g. CREDITS ADD 21000")
        return
    expiry = 30 * 60 # 30 minutes
    memo = f"Add {amount} credits to Zapping Bot for {npub}"
    newInvoice = lnd.createInvoice(amount, memo, expiry)
    if newInvoice is None:
        logger.warning("Error creating invoice for npub {npub} in the amount {amount}")
        sendDirectMessage(npub, "Unable to create an invoice at this time. Please contact operator")
        return
    # save the current invoice
    payment_request = newInvoice["payment_request"]
    created_at, created_at_iso = utils.getTimes()
    expiry_time = datetime.now() + timedelta(seconds=expiry)
    expiry_time_int, expiry_time_iso = utils.getTimes(expiry_time)
    currentInvoice["npub"] = npub
    currentInvoice["created_at"] = created_at
    currentInvoice["created_at_iso"] = created_at_iso
    currentInvoice["amount"] = amount
    currentInvoice["memo"] = memo
    currentInvoice["expiry"] = expiry
    currentInvoice["expiry_time"] = expiry_time_int
    currentInvoice["expiry_time_iso"] = expiry_time_iso
    currentInvoice["r_hash"] = newInvoice["r_hash"]
    currentInvoice["payment_request"] = payment_request
    currentInvoice["add_index"] = newInvoice["add_index"]
    setNostrFieldForNpub(npub, "currentInvoice", currentInvoice)
    # save to outstanding invoices
    lnd.monitorInvoice(currentInvoice)
    # send back response
    message = "Please fulfill the following invoice to credit the account"
    message = f"{message}\n\n{payment_request}"
    sendDirectMessage(npub, message)

def getCreditsSummary(npub):
    filename = ledger.getUserLedgerFilename(npub)
    ledgerLines = files.loadJsonFile(filename)
    ledgerSummary = {
        "CREDITS APPLIED": 0,
        "ZAPS": 0,
        "ROUTING FEES": 0,
        "SERVICE FEES": 0
    }
    for ledgerEntry in ledgerLines:
        type = ledgerEntry["type"]
        credits = ledgerEntry["credits"]
        mcredits = ledgerEntry["mcredits"]
        if type in ledgerSummary:
            value = ledgerSummary[type]
            value += credits
            value += (mcredits/1000)
            ledgerSummary[type] = value
    text = ""
    maxFieldValueLength = 0
    # round up to whole numbers
    for k, v in ledgerSummary.items():
        v = int(v)
        ledgerSummary[k] = v
        if len(v) > maxFieldValueLength: maxFieldValueLength = len(v)
    for k, v in ledgerSummary.items():
        text = f"{text}\n{k: >18}: {v: >maxFieldValueLength}"
    return text

def handleStatus(npub, content):
    words = content.split()
    if len(words) > 1:
        logger.warning("User {npub} called STATUS and provided arguments: {words[1:]}")
    npubConfig = getNpubConfigFile(npub)
    relaysCount = len(npubConfig["relays"])
    conditionsCount = len(npubConfig["conditions"])
    eventIdhex = npubConfig["eventId"]
    eventIdbech32 = utils.hexToBech32(eventIdhex, "nevent")
    shorthex = eventIdhex[0:6] + ".." + eventIdhex[-6:]
    #shortbech32 = eventIdbech32[0:12] + ".." + eventIdbech32[-6:]
    maxZap = 0
    zapMessage = npubConfig["zapMessage"]
    creditsSummary = getCreditsSummary(npub)
    message = f"The bot is configured with {relaysCount} relays, {conditionsCount} conditions, and monitoring event {shorthex}."
    message = f"{message}\n\nResponses to the event matching conditions will be zapped up to {maxZap} with the following message: {zapMessage}"
    message = f"{message}\n{creditsSummary}"
    sendDirectMessage(npub, message)

def handleSupport(npub, content):
# SUPPORT <message to send to support>
    words = content.split()
    if len(words) > 1:
        message = " ".join(words[1:])
        message = "Message relayed from {npub} about Zapper Bot: {message}"
        operatornpub = getOperatorNpub()
        if operatornpub is not None:
            sendDirectMessage(operatornpub, message)
            # reply to user
            message = f"Your message has been forwarded through nostr relays. The operator may reach out to you directly or through other channels.  If you need to temporarily stop the bot, you can set the event identifier to 0."
            sendDirectMessage(npub, message)
        else:
            # notify user of bad config
            message = f"Your message could not be forwarded. Operator npub not configured. If you know the operator, contact them directly."
            sendDirectMessage(npub, message)
