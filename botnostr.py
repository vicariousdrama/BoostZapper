#!/usr/bin/env python3
from collections import OrderedDict
from datetime import datetime, timedelta
from nostr.key import PrivateKey, PublicKey
from nostr.event import Event, EventKind, EncryptedDirectMessage
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
from nostr.relay_manager import RelayManager
import bech32
import json
import random
import re
import ssl
import time
import botfiles as files
import botutils as utils
import botledger as ledger
import botlnd as lnd
import botlnurl as lnurl

logger = None
config = None
handledMessages = {}
botRelayManager = None
handledEvents = {}

def connectToRelays():
    global botRelayManager
    botRelayManager = RelayManager()
    relays = getNostrRelaysFromConfig(config)
    for nostrRelay in relays:
        if type(nostrRelay) is dict:
            botRelayManager.add_relay(url=nostrRelay["url"],read=nostrRelay["read"],write=nostrRelay["write"])
        if type(nostrRelay) is str:
            botRelayManager.add_relay(url=nostrRelay)
    botRelayManager.open_connections({"cert_reqs": ssl.CERT_NONE})

def getNpubConfigFilename(npub):
    return f"{files.userConfigFolder}{npub}.json"

def getNpubConfigFile(npub):
    filename = getNpubConfigFilename(npub)
    npubConfig = files.loadJsonFile(filename)
    if npubConfig is None: return {}
    return npubConfig

def getBotPrivateKey():
    if "botnsec" not in config: 
        logger.warning("Server config missing 'botnsec' in nostr section.")
        quit()
    botNsec = config["botnsec"]
    if botNsec is None or len(botNsec) == 0:
        logger.warning("Server config missing 'botnsec' in nostr section.")
        quit()
    botPrivkey = PrivateKey().from_nsec(botNsec)
    return botPrivkey

def getBotPubkey():
    botPrivkey = getBotPrivateKey()
    if botPrivkey is None: return None
    return botPrivkey.public_key.hex()

def getOperatorNpub():
    if "operatornpub" not in config:
        logger.warning("Server config missing 'operatornpub' in nostr section.")
        return None
    operatornpub = config["operatornpub"]
    return operatornpub

def sendDirectMessage(npub, message):
    if npub is None:
        logger.warning("Unable to send direct message to recipient npub (value is None).")
        logger.warning(f" - message: {message}")
        return
    botPubkey = getBotPubkey()
    if botPubkey is None:
        logger.warning("Unable to send direct message to npub.")
        logger.warning(f" - npub: {npub}")
        logger.warning(f" - message: {message}")
        return
    recipient_pubkey = PublicKey().from_npub(npub).hex()
    dm = EncryptedDirectMessage(
        recipient_pubkey=recipient_pubkey,
        cleartext_content=message
    )
    getBotPrivateKey().sign_event(dm)
    botRelayManager.publish_event(dm)

def removeSubscription(relaymanager, subid):
    # relaymanager.close_subscription(subid)
    # temp workaround to faulty logi in nostr/relay.py#103 for close_subscription
    for relay in relaymanager.relays.values():
        if subid in relay.subscriptions.keys():
            with relay.lock:
                relay.subscriptions.pop(subid)


def checkDirectMessages():
    global handledMessages          # tracked in this file, and only this function
    botPubkey = getBotPubkey()
    if botPubkey is None:
        logger.warning("Unable to check direct messages.")
        return
    newMessages = []
    t, _ = utils.getTimes()
    since = t - 300 # 5 minutes ago
    # remove older from handled
    stillGood = {}
    for k,v in handledMessages.items():
        if v >= since:
            stillGood[k] = v
    handledMessages = stillGood
    # setup filter to retrieve direct messages sent to us
    filters = Filters([Filter(
        since=since,
        pubkey_refs=[botPubkey],
        kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE]
        )])
    subscription_id = f"inbox-{since}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    botRelayManager.add_subscription(subscription_id, filters)
    message = json.dumps(request)
    botRelayManager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # wait for events to return, gather and close
    while botRelayManager.message_pool.has_events():
        event_msg = botRelayManager.message_pool.get_event()
        # only add those not already in the handledMessages list
        if event_msg.event.id not in handledMessages:
            newMessages.append(event_msg)
            handledMessages[event_msg.event.id] = event_msg.event.created_at
    removeSubscription(botRelayManager, subscription_id)
    return newMessages

def isValidSignature(event): 
    sig = event.signature
    id = event.id
    publisherPubkey = event.public_key
    pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey))
    return pubkey.verify_signed_message_hash(hash=id, sig=sig)

def processDirectMessages(messages):
    botPK = getBotPrivateKey()
    for message in messages:
        if not isValidSignature(message.event): continue
        publisherHex = str(message.event.public_key).strip()
        npub = PublicKey(raw_bytes=bytes.fromhex(publisherHex)).bech32()
        content = str(message.event.content).strip()
        content = botPK.decrypt_message(content, publisherHex)
        logger.debug(f"{npub} command via DM: {content}")
        firstWord = content.split()[0].upper()
        if firstWord == "HELP":
            handleHelp(npub, content)
        elif firstWord == "FEES":
            handleFees(npub, content)
        elif firstWord == "RELAYS":
            handleRelays(npub, content)
        elif firstWord == "CONDITIONS":
            handleConditions(npub, content)
        elif firstWord == "EXCLUDES":
            handleExcludes(npub, content)
        elif firstWord == "PROFILE":
            handleProfile(npub, content)
        elif firstWord == "ZAPMESSAGE":
            handleZapMessage(npub, content)
        elif firstWord == "EVENT":
            handleEvent(npub, content)
        elif firstWord == "EVENTBUDGET":
            handleEventBudget(npub, content)
        elif firstWord == "BALANCE":
            handleBalance(npub, content)
        elif firstWord == "CREDITS":
            handleCredits(npub, content)
        elif firstWord == "STATUS":
            handleStatus(npub, content)
        elif firstWord == "ENABLE":
            handleEnable(npub, True)
        elif firstWord == "DISABLE":
            handleEnable(npub, False)
        elif firstWord == "SUPPORT":
            handleSupport(npub, content)
        else:
            handleHelp(npub, content)

def handleHelp(npub, content):
    words = content.split()
    handled = False
    message = ""
    if len(words) > 1:
        secondWord = str(words[1]).upper()
        if secondWord == "FEES":
            message = "Return the fee rates for the service"
            handled = True
        elif secondWord == "RELAYS":
            message = "Relays commands:"
            message = f"{message}\nRELAYS LIST"
            message = f"{message}\nRELAYS ADD <relayUrl> [--canRead] [--canWrite]"
            message = f"{message}\nRELAYS DELETE <index>"
            message = f"{message}\nRELAYS CLEAR"
            handled = True
        elif secondWord == "CONDITIONS":
            message = "Conditions commands:\nCONDITIONS LIST"
            message = f"{message}\nCONDITIONS ADD [--amount <zap amount if matched>] [--randomWinnerLimit <number of random winners of this amount for the event>] [--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>] [--requiredRegex <regular expression to match>] [--replyMessage <message to reply with if matched>]"
            message = f"{message}\nCONDITIONS UP <index>"
            message = f"{message}\nCONDITIONS DELETE <index>"
            message = f"{message}\nCONDITIONS CLEAR"
            handled = True
        elif secondWord == "EXCLUDES":
            message = "Excludes commands:"
            message = f"{message}\nEXCLUDES LIST"
            message = f"{message}\nEXCLUDES ADD <exclude phrase or npub>"
            message = f"{message}\nEXCLUDES DELETE <index>"
            message = f"{message}\nEXCLUDES CLEAR"
            handled = True
        elif secondWord == "PROFILE":
            message = "Profile commands:"
            message = f"{message}\nPROFILE [--name <name>] [--picture <url for profile picture>] [--banner <url for profile banner>] [--description <description of account>] [--nip05 <nip05 to assign>] [--lud16 <lightning address>]"
            message = f"{message}\nSpecifying PROFILE without arguments will output the current profile"
            handled = True
        elif secondWord == "ZAPMESSAGE":
            message = "Zap Message commands:"
            message = f"{message}\nZAPMESSAGE <message to send with zap>"
            handled = True
        elif secondWord == "EVENT":
            message = "Event commands:"
            message = f"{message}\nEVENT <event identifier>"
            handled = True
        elif secondWord == "EVENTBUDGET":
            message = "Set a limit to be spent on the current event"
            message = f"{message}\nEVENTBUDGET 21000"
            handled = True
        elif secondWord == "BALANCE":
            message = "Get the balance of credits for your bot."
            handled = True
        elif secondWord == "CREDITS":
            message = "Credits commands:"
            message = f"{message}\nCREDITS ADD <amount>"
            handled = True
        elif secondWord == "ENABLE":
            message = "Enable your bot to process events if configuration is valid."
            message = f"{message}\nTo disable, use the DISABLE command."
            handled = True
        elif secondWord == "DISABLE":
            message = "Disable your bot from processing events."
            handled = True
        elif secondWord == "STATUS":
            message = "Reports the current summary status for your bot account."
            handled = True
        elif secondWord == "SUPPORT":
            message = "Attempts to forward a message to the operator of the service."
            message = f"{message}\nSUPPORT <message to send to support>"
            handled = True
    if not handled:
        message = "This bot can zap responses to an event you set with conditions. To get detailed help, issue the subcommand after the HELP option (e.g. HELP RELAYS)."
        message = f"{message}\nCommands: FEES, RELAYS, CONDITIONS, PROFILE, ZAPMESSAGE, EVENT, EVENTBUDGET, BALANCE, CREDITS, ENABLE, DISABLE, STATUS, SUPPORT"
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
    relays = getNostrRelaysFromConfig(npubConfig)
    if len(relays) == 0:
        relays = getNostrRelaysFromConfig(config)
    return relays

def getNostrRelaysFromConfig(aConfig):
    relays = []
    relayUrls = []
    if "relays" in aConfig:
        for relay in aConfig["relays"]:
            relayUrl = ""
            canRead = True
            canWrite = True
            if type(relay) is str:
                relayUrl = relay
            if type(relay) is dict:
                if "url" not in relay: continue
                relayUrl = relay["url"]
                canRead = relay["read"] if "canRead" in relay else canRead
                canWrite = relay["write"] if "canWrite" in relay else canWrite
            relayUrl = relayUrl if str(relayUrl).startswith("wss://") else f"wss://{relayUrl}"
            if relayUrl not in relayUrls:
                relayUrls.append(relayUrl)
                relays.append({"url":relayUrl,"read":canRead,"write":canWrite})
    return relays

def handleFees(npub, content):
    feesReplyMessage = 20
    feesZapEvent = 20
    feesTime864 = 1000
    fees = None
    if "fees" in config: fees = config["fees"]
    if fees is not None:
        if "replyMessage" in fees: feesReplyMessage = fees["replyMessage"]
        if "zapEvent" in fees: feesZapEvent = fees["zapEvent"]
        if "time864" in fees: feesTime864 = fees["time864"]
    message = "Current Fee Rates:"
    message = f"{message}\n- each event zapped: {feesZapEvent} millicredits"
    message = f"{message}\n- each reply message: {feesReplyMessage} millicredits"
    message = f"{message}\n- time units: {feesTime864} millicredits"
    message = f"{message}\n  (a time unit is 1/100th of the day, or 864 seconds of the bot monitoring events)"
    sendDirectMessage(npub, message)

def handleRelays(npub, content):
    singular = "Relay"
    plural = "Relays"
    pluralLower = str(plural).lower()
    pluralupper = str(plural).upper()
    relaysReset = False
    words = content.split()
    if len(words) > 1:
        secondWord = str(words[1]).upper()
        if secondWord == "DELETE":
            handleGenericList(npub, content, singular, plural)
            return
        npubConfig = getNpubConfigFile(npub)
        theList = npubConfig[pluralLower] if pluralLower in npubConfig else []
        if secondWord in ("CLEAR", "RESET"):
            relaysReset = True
            theList = config["relays"]
            setNostrFieldForNpub(npub, pluralLower, theList)
        if secondWord in ("ADD"):
            url = None
            canRead = True if len(words) < 3 else False
            canWrite = True if len(words) < 3 else False
            for word in words[2:]:
                if str(word).startswith("--"):
                    flagWord = str(word[2:]).lower()
                    if flagWord == "canread": canRead = True
                    if flagWord == "canwrite": canWrite = True
                else:
                    url = word if url is None else url
            if url is None:
                message = "Please provide url of relay to add in wss://relay.domain format"
                sendDirectMessage(npub, message)
                return
            url = url if str(url).startswith("wss://") else f"wss://{url}"
            # transform list if it has strings
            hasStrings = False
            newList = []
            for item in theList:
                if type(item) is str:
                    hasStrings = True
                    newItem = {"url":item, "read": True, "write": True}
                    newList.append(newItem)
                if type(item) is dict:
                    newList.append(item)                   
            if hasStrings: theList = newList
            # look for existing relay url in list
            found = False
            for item in theList:
                if type(item) is dict:
                    if "url" in item and item["url"] == url:
                        # existing found, update it
                        found = True
                        item["read"] = canRead
                        item["write"] = canWrite
            # not found, add it
            if not found:
                item = {"url": url, "read": canRead, "write": canWrite}
                theList.append(item)
            # save changes
            setNostrFieldForNpub(npub, pluralLower, theList)
    else:
        npubConfig = getNpubConfigFile(npub)
        theList = npubConfig[pluralLower] if pluralLower in npubConfig else []
    # List
    idx = 0
    message = f"{plural}:"
    if len(theList) > 0:
        for item in theList:
            idx += 1
            desc = ""
            perm = ""
            if type(item) is str: desc = f"{item} [rw]"
            if type(item) is dict:
                if "url" in item: desc = item["url"]
                if "read" in item and item["read"]: perm = f"{perm}r"
                if "write" in item and item["write"]: perm = f"{perm}w"
                if len(perm) > 0: desc = f"{desc} [{perm}]"
            message = f"{message}\n{idx}) {desc}"
        if relaysReset:
            message = f"{message}\n\nRelay list was reset to defaults"
    else:
        message = f"{message}\n\n{singular} list is empty"
    sendDirectMessage(npub, message)

def handleExcludes(npub, content):
    handleGenericList(npub, content, "Exclude", "Excludes")

def handleGenericList(npub, content, singular, plural):
    npubConfig = getNpubConfigFile(npub)
    pluralLower = str(plural).lower()
    pluralupper = str(plural).upper()
    theList = npubConfig[pluralLower] if pluralLower in npubConfig else []
    words = content.split()
    if len(words) > 1:
        secondWord = str(words[1]).upper()
        if secondWord == "CLEAR":
            theList = []
            setNostrFieldForNpub(npub, pluralLower, theList)
        if secondWord == "ADD":
            if len(words) > 2:
                itemValue = words[2]
                if itemValue not in theList:
                    theList.append(itemValue)
                    setNostrFieldForNpub(npub, pluralLower, theList)
            else:
                sendDirectMessage(npub, f"Please provide the value to add to the {singular} list\n{pluralupper} ADD value-here")
                return
        if secondWord == "DELETE":
            if len(words) <= 2:
                sendDirectMessage(npub, f"Please provide the index of the item to remove from the {singular} list\n{pluralupper} DELETE 2")
                return
            value2Delete = words[2]
            if str(value2Delete).isdigit():
                idxNum = int(value2Delete)
                if idxNum <= 0:
                    sendDirectMessage(npub, f"Please provide the index of the {singular} item to be deleted\n{pluralupper} DELETE 3")
                    return
                if idxNum > len(theList):
                    sendDirectMessage(npub, f"Index not found in {singular} list")
                else:
                    idxNum -= 1 # 0 based
                    del theList[idxNum]
                    setNostrFieldForNpub(npub, pluralLower, theList)
            else:
                if value2Delete in theList:
                    theList.remove(value2Delete)
                    setNostrFieldForNpub(npub, pluralLower, theList)
                else:
                    sendDirectMessage(npub, f"Item not found in {singular} list")
    # If still here, send the list
    idx = 0
    message = f"{plural}:"
    if len(theList) > 0:
        for item in theList:
            idx += 1
            message = f"{message}\n{idx}) {item}"
    else:
        message = f"{message}\n\n{singular} list is empty"
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
    supportedArguments = {
        "amount": "amount", 
        "requiredlength": "requiredLength", 
        "requiredphrase": "requiredPhrase", 
        "requiredregex": "requiredRegex", 
        "randomwinnerlimit": "randomWinnerLimit",
        "replymessage": "replyMessage"
    }
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
                    "requiredlength":0,
                    "requiredphrase":None
                    }
                for word in words[2:]:
                    # check if starting a new argument
                    if len(word) > 2 and str(word).startswith("--"):
                        argWord = str(word[2:]).lower()
                        if argWord in supportedArguments.keys():
                            # if ended an argument, need to assign value
                            if commandWord is not None:
                                # numbers
                                if commandWord in ["amount","requiredlength","randomwinnerlimit"]:
                                    if str(combinedWords).isdigit():
                                        newCondition[supportedArguments[commandWord]] = int(combinedWords)
                                # all others are strings
                                else:
                                    newCondition[supportedArguments[commandWord]] = combinedWords
                            commandWord = argWord
                            combinedWords = ""
                    else:
                        # not starting an argument, build composite value
                        combinedWords = f"{combinedWords} {word}" if len(combinedWords) > 0 else word
                # check if have a composite value needing assigned
                if commandWord is not None:
                    # numbers
                    if commandWord in ["amount","requiredlength","randomwinnerlimit"]:
                        if str(combinedWords).isdigit():
                            newCondition[supportedArguments[commandWord]] = int(combinedWords)
                    # all others are strings
                    else:
                        newCondition[supportedArguments[commandWord]] = combinedWords
                    combinedWords = ""
                # validate before adding
                if newCondition["amount"] < 0:
                    sendDirectMessage(npub, "Amount for new condition must be greater than or equal to 0")
                    return
                conditions.append(newCondition)
                setNostrFieldForNpub(npub, "conditions", conditions)
            else:
                message = "Please provide the condition to be added using the command format:\nCONDITIONS ADD [--amount <zap amount if matched>][--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>]"
                message = f"{message}\n\nExample:\nCONDITIONS ADD --amount 20 --requiredPhrase Nodeyez"
                sendDirectMessage(npub, message)
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
    message = "Conditions/Rules based on response message content:"
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
            if "requiredRegex" in condition:
                conditionRequiredRegex = condition["requiredRegex"]
                if conditionRequiredRegex is not None and len(conditionRequiredRegex) > 0:
                    message = f"{message} if" if rCount == 0 else f"{message} and"
                    message = f"{message} matches regular expression {conditionRequiredRegex}"
                    rCount += 1
            if "randomWinnerLimit" in condition:
                randomWinnerLimit = condition["randomWinnerLimit"]
                if randomWinnerLimit is not None and randomWinnerLimit > 0:
                    message = f"{message} if" if rCount == 0 else f"{message} and"
                    message = f"{message} one of {randomWinnerLimit} randomly selected winners"
            if "replyMessage" in condition:
                replyMessage = condition["replyMessage"]
                if replyMessage is not None and len(replyMessage) > 0:
                    message = f"{message}, send reply message: {replyMessage}."
    else:
        message = f"{message}\n\nCondition list is empty"
    sendDirectMessage(npub, message)

def getNostrProfileForNpub(npub):
    # this is the bot profile from config, not from kind0
    npubConfig = getNpubConfigFile(npub)
    if "profile" in npubConfig:
        return npubConfig["profile"], False
    else:
        newPrivateKey = PrivateKey()
        newProfile = dict(config["defaultProfile"])
        newProfile["nsec"] = newPrivateKey.bech32()
        newProfile["npub"] = newPrivateKey.public_key.bech32()
        setNostrFieldForNpub(npub, "profile", newProfile)
        return newProfile, True

def handleProfile(npub, content):
    profile, hasChanges = getNostrProfileForNpub(npub)
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
                combinedWords = f"{combinedWords} {word}" if len(combinedWords) > 0 else word                
        if commandWord is not None:
            if profile[commandWord] != combinedWords:
                hasChanges = True
            profile[commandWord] = combinedWords
        if hasChanges:
            setNostrFieldForNpub(npub, "profile", profile)
            publishProfile(npub)
    # Report fields in profile (except nsec)
    message = "Profile information:\n"
    for k, v in profile.items():
        if k not in ("nsec"):
            v1 = "not defined" if v is None or len(v) == 0 else v
            message = f"{message}\n{k}: {v1}"
    sendDirectMessage(npub, message)

def getProfileForNpubFromRelays(subBotNpub=None, lookupNpub=None):
    relayProfile = {}
    if lookupNpub is None: return None
    # filter setup
    filters = Filters([Filter(kinds=[EventKind.SET_METADATA],authors=[lookupNpub])])
    t, _ = utils.getTimes()
    subscription_id = f"profile-{lookupNpub[0:4]}..{lookupNpub[-4:]}-{t}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    message = json.dumps(request)
    relayManager = None
    if subBotNpub is None:
        # use botRelayManager
        relayManager = botRelayManager
    else:
        # set localRelayManager
        # -- bots for npubs can have their own relays
        relays = getNostrRelaysForNpub(subBotNpub)
        localRelayManager = RelayManager()
        for nostrRelay in relays:
            if type(nostrRelay) is dict:
                localRelayManager.add_relay(url=nostrRelay["url"],read=nostrRelay["read"],write=nostrRelay["write"])
            if type(nostrRelay) is str:
                localRelayManager.add_relay(url=nostrRelay)
        localRelayManager.add_subscription(subscription_id, filters)
        localRelayManager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
        time.sleep(1.25) # allow the connections to open
        relayManager = localRelayManager
    relayManager.add_subscription(subscription_id, filters)
    relayManager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # look over returned events
    created_at = 0
    while relayManager.message_pool.has_events():
        event_msg = relayManager.message_pool.get_event()
        if event_msg.event.created_at < created_at: continue
        if not isValidSignature(event_msg.event): continue
        try:
            ec = json.loads(event_msg.event.content)
            created_at = event_msg.event.created_at
            relayProfile = dict(ec)
        except Exception as err:
            continue
    removeSubscription(relayManager, subscription_id)
    if subBotNpub is not None:
        localRelayManager.close_connections()
    return relayProfile

def checkBotProfile():
    botPubkey = getBotPubkey()
    profileOnRelays = getProfileForNpubFromRelays(None, botPubkey)
    needsUpdated = False
    if profileOnRelays is None:
        needsUpdated = True
    if not needsUpdated:
        configProfile = config["botProfile"]
        kset = ("name","description","nip05","lud16","picture","banner")    
        for k in kset: 
            if k in configProfile:
                if k not in profileOnRelays:
                    if len(configProfile[k]) > 0:
                        needsUpdated = True
                        break
                elif configProfile[k] != profileOnRelays[k]:
                    needsUpdated = True
                    break
    if needsUpdated:
        publishBotProfile()

def publishBotProfile():
    profilePK = getBotPrivateKey()
    profile = config["botProfile"]
    j = {}
    kset = ("name","description","nip05","lud16","picture","banner")
    for k in kset: 
        if k in profile and len(profile[k]) > 0: j[k] = profile[k]
    content = json.dumps(j)
    publickeyhex = profilePK.public_key.hex()
    kind0 = Event(
        content=content,
        public_key=publickeyhex,
        kind=EventKind.SET_METADATA,
        )
    profilePK.sign_event(kind0)
    botRelayManager.publish_event(kind0)

def publishProfile(npub):
    profile, _ = getNostrProfileForNpub(npub)
    j = {}
    kset = ("name","description","nip05","lud16","picture","banner")
    for k in kset: 
        if k in profile and len(profile[k]) > 0: j[k] = profile[k]
    content = json.dumps(j)
    profileNsec = profile["nsec"]
    profilePK = PrivateKey().from_nsec(profileNsec)
    publickeyhex = profilePK.public_key.hex()
    kind0 = Event(
        content=content,
        public_key=publickeyhex,
        kind=EventKind.SET_METADATA,
        )
    profilePK.sign_event(kind0)
    botRelayManager.publish_event(kind0)

def handleZapMessage(npub, content):
    zapMessage = getNostrFieldForNpub(npub, "zapMessage")
    words = content.split()
    if len(words) > 1:
        zapMessage = " ".join(words[1:])
        setNostrFieldForNpub(npub, "zapMessage", zapMessage)
    if len(zapMessage) > 0:
        message = f"The zap message is set to: {zapMessage}"
    else:
        message = f"The zap message has not yet been set. Specify the message as follows\n\nZAPMESSAGE Comment to send with zaps"
    sendDirectMessage(npub, message)

def handleEventBudget(npub, content):
    eventId = getNostrFieldForNpub(npub, "eventId")
    budgetWord = getNostrFieldForNpub(npub, "eventBudget")
    budget = 0
    if budgetWord is not None and str(budgetWord).isdigit():
        budget = int(budgetWord)
    words = content.split()
    if len(words) > 1:
        budgetWord = words[1]
        if not str(budgetWord).isdigit():
            message = f"Please specify the budget amount as a whole number"
            sendDirectMessage(npub, message)
            return
        else:
            budget = int(budgetWord)
            if budget <= 0:
                setNostrFieldForNpub(npub, "eventBudget", None)
            else:
                setNostrFieldForNpub(npub, "eventBudget", budget)
    # calculate spent and balance
    balance = ledger.getCreditBalance(npub)
    eventSpent = getEventSpentSoFar(npub, eventId)
    eventBalance = float(budget) - float(eventSpent) if budget > 0 else float(balance)
    setNostrFieldForNpub(npub, "eventBalance", eventBalance)
    # report current budget info
    budgetWord = "unlimited" if budget <= 0 else str(budget)
    message = f"The budget for the event has been set to {budgetWord}."
    message = f"{message} {eventSpent} credits have been used to date for the event"
    if budget > 0:
        if eventBalance > 0:
            message = f"{message}, leaving {eventBalance} remaining."
        else:
            message = f"{message}. Zaps and replies for this event will not be performed."
    message = f"{message} Your account balance is {balance}."
    sendDirectMessage(npub, message)

def handleEvent(npub, content):
    currentEventId = getNostrFieldForNpub(npub, "eventId")
    words = content.split()
    if len(words) > 1:
        eventId = words[1]
        eventId = utils.normalizeToBech32(eventId, "nevent")
        setNostrFieldForNpub(npub, "eventId", eventId)
    newEventId = getNostrFieldForNpub(npub, "eventId")
    if currentEventId != newEventId:
        setNostrFieldForNpub(npub, "eventCreated", 0)
        setNostrFieldForNpub(npub, "eventSince", 0)
        eventBudget = getNostrFieldForNpub(npub, "eventBudget")
        # determine amount spent already and get balance based on budget
        setNostrFieldForNpub(npub, "eventBalance", None)
        if eventBudget is not None and str(eventBudget).isnumeric():
            if float(eventBudget) > 0:
                eventSpent = getEventSpentSoFar(npub, newEventId)
                eventBalance = float(eventBudget) - float(eventSpent)
                setNostrFieldForNpub(npub, "eventBalance", eventBalance)        
    if newEventId is None or len(newEventId) == 0:
        message = "No longer monitoring an event"
    else:
        shortbech32 = newEventId[0:12] + ".." + newEventId[-6:]
        message = f"Now monitoring event {shortbech32} ({newEventId})"
    sendDirectMessage(npub, message)

def getEventSpentSoFar(npub, eventId):
    eventSpent = float(0)
    feesZapEvent = 50
    feesReplyMessage = 50
    if "fees" in config: fees = config["fees"]
    if fees is not None:
        if "replyMessage" in fees: feesReplyMessage = fees["replyMessage"]
        if "zapEvent" in fees: feesZapEvent = fees["zapEvent"]
    basePath = f"{files.userEventsFolder}{npub}/{eventId}/"
    utils.makeFolderIfNotExists(basePath)
    filePaidNpubs = f"{basePath}paidnpubs.json"
    paidnpubs = files.loadJsonFile(filePaidNpubs, {})
    for v in paidnpubs.values():
        amount = v["amount_sat"] if "amount_sat" in v else 0
        routingfee = v["fee_msat"] if "fee_msat" in v else 0
        eventSpent += float(amount)
        eventSpent += float(float(routingfee)/float(1000))
        eventSpent += float(float(feesZapEvent)/float(1000))
    fileReplies = f"{basePath}replies.json"
    replies = files.loadJsonFile(fileReplies, [])
    eventSpent += (len(replies) * (float(feesReplyMessage)/float(1000)))
    return eventSpent

def handleBalance(npub, content):
    balance = ledger.getCreditBalance(npub)
    sendDirectMessage(npub, f"Your balance is {balance}. To add credits, specify the full command. e.g. CREDITS ADD 21000")

def handleCredits(npub, content):
    # See if there is an existing unexpired invoice
    currentInvoice = getNostrFieldForNpub(npub, "currentInvoice")
    if type(currentInvoice) is dict and len(currentInvoice.keys()) > 0:
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
        balance = ledger.getCreditBalance(npub)
        sendDirectMessage(npub, f"Your balance is {balance}. To add credits, specify the full command. e.g. CREDITS ADD 21000")
        return
    expiry = 30 * 60 # 30 minutes
    memo = f"Add {amount} credits to Zapping Bot for {npub}"
    ledger.recordEntry(npub, "INVOICE CREATED", 0, 0, memo)
    newInvoice = lnd.createInvoice(amount, memo, expiry)
    if newInvoice is None:
        logger.warning(f"Error creating invoice for npub {npub} in the amount {amount}")
        sendDirectMessage(npub, "Unable to create an invoice at this time. Please contact operator")
        return
    # save the current invoice
    payment_request = newInvoice["payment_request"]
    created_at, created_at_iso = utils.getTimes()
    expiry_time = datetime.utcnow() + timedelta(seconds=expiry)
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
    if ledgerLines is None: ledgerLines = []
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
    # round up to whole numbers
    for k, v in ledgerSummary.items():
        v = int(v)
        ledgerSummary[k] = v
    for k, v in ledgerSummary.items():
        text = f"{text}\n{k: >18}: {str(v): >8}"
    balance = ledger.getCreditBalance(npub)
    text = f"{text}\n{'BALANCE': >18}: {str(balance): >8}"
    return text

def handleEnable(npub, isEnabled):
    if not isEnabled:
        setNostrFieldForNpub(npub, "enabled", isEnabled)
        sendDirectMessage(npub, "Bot disabled. Events will not be processed until re-enabled")
        return
    # validation
    relays = getNostrRelaysForNpub(npub)
    if len(relays) == 0:
        sendDirectMessage(npub, "Unable to enable bot. There must be at least one relay defined. Use RELAYS ADD <relay>")
        return
    conditions = getNostrConditionsForNpub(npub)
    if len(conditions) == 0:
        sendDirectMessage(npub, "Unable to enable the bot. There must be at least one condition. Use CONDITIONS ADD [--amount <zap amount if matched>] [--randomWinnerLimit <number of random winners of this amount for the event>] [--requiredLength <length required to match>] [--requiredPhrase <phrase required to match>] [--requiredRegex <regular expression to match>] [--replyMessage <message to reply with if matched>]")
        return
    zapMessage = getNostrFieldForNpub(npub, "zapMessage")
    if len(zapMessage) == 0:
        sendDirectMessage(npub, "Unable to enable the bot. The zap message must be set. Use ZAPMESAGE <message to send users>")
        return
    eventId = getNostrFieldForNpub(npub, "eventId")
    if len(eventId) == 0:
        sendDirectMessage(npub, "Unable to enable the bot. The eventId must be set. Use EVENT <event identifier>")
        return
    balance = ledger.getCreditBalance(npub)
    if balance < 5:
        sendDirectMessage(npub, "Unable to enable the bot. Funds required. Use CREDIT ADD <amount>")
        return
    # once reached here, ok to enable
    setNostrFieldForNpub(npub, "enabled", isEnabled)
    sendDirectMessage(npub, "Bot enabled!")

def handleStatus(npub, content):
    helpMessage = None
    words = content.split()
    if len(words) > 1:
        logger.warning(f"User {npub} called STATUS and provided arguments: {words[1:]}")
    npubConfig = getNpubConfigFile(npub)
    relaysCount = 0
    if "relays" in npubConfig: 
        relaysCount = len(npubConfig["relays"])
    else:
        relaysCount = len(config["relays"])
    if helpMessage is None and relaysCount == 0: helpMessage = "Use RELAYS ADD command to configure relays"
    conditionsCount = 0
    maxZap = 0
    if "conditions" in npubConfig: 
        conditionsCount = len(npubConfig["conditions"])
        for condition in npubConfig["conditions"]:
            if condition["amount"] > maxZap: 
                maxZap = condition["amount"]
    if helpMessage is None and conditionsCount == 0: helpMessage = "Use CONDITIONS ADD command to define a rule for zapping"
    eventId = None
    if "eventId" in npubConfig:
        eventId = npubConfig["eventId"]
        if utils.isHex(eventId): 
            eventIdHex = eventId
            eventIdbech32 = utils.hexToBech32(eventIdHex, "nevent")
        else:
            eventIdHex = utils.bech32ToHex(eventId)
            eventIdbech32 = eventId
    if helpMessage is None and eventId is None: helpMessage = "Use the EVENT command to set the event to be monitored"
    zapMessage = None
    if "zapMessage" in npubConfig: zapMessage = npubConfig["zapMessage"]
    creditsSummary = getCreditsSummary(npub)
    message = f"The bot is configured with {relaysCount} relays"
    message = f"{message}, {conditionsCount} conditions"
    if eventId is None:
        message = f"{message}, but has no event to monitor defined."
    else:
        message = f"{message}, and monitoring the following event {eventIdbech32}."
    message = f"{message}\n\nResponses to the event matching conditions will be zapped up to {maxZap}"
    if zapMessage is not None:
        message = f"{message} with the following message: {zapMessage}"
    else:
        if helpMessage is None: helpMessage = "Use the ZAPMESSAGE command to set the comment to include in zaps"
    message = f"{message}\n{creditsSummary}"
    if "enabled" in npubConfig and npubConfig["enabled"]:
        message = f"{message}\nBot is enabled"
    else:
        message = f"{message}\nBot is not currently enabled"
    if helpMessage is not None:
        message = f"{message}\n\n{helpMessage}"
    sendDirectMessage(npub, message)

def handleSupport(npub, content):
# SUPPORT <message to send to support>
    words = content.split()
    if len(words) > 1:
        message = " ".join(words[1:])
        message = f"Message relayed from {npub} about Zapper Bot: {message}"
        operatornpub = getOperatorNpub()
        if operatornpub is not None:
            sendDirectMessage(operatornpub, message)
            # reply to user
            message = f"Your message has been forwarded through nostr relays. The operator may reach out to you directly or through other channels.  If you need to temporarily stop the bot, you can use the DISABLE command or set EVENT 0"
            sendDirectMessage(npub, message)
        else:
            # notify user of bad config
            message = f"Your message could not be forwarded. Operator npub not configured. If you know the operator, contact them directly."
            sendDirectMessage(npub, message)

def getEnabledBots():
    logger.debug("Checking bots for events")
    enabledBots = OrderedDict()
    botConfigs = files.listUserConfigs()
    for botConfigFile in botConfigs:
        npub = botConfigFile.split(".")[0]
        npub2 = PublicKey().from_npub(npub).bech32()
        if npub != npub2: 
            logger.warning(f"in getEnabledBots, {npub} does not match {npub2}")
            continue
        filename = f"{files.userConfigFolder}{botConfigFile}"
        botConfig = files.loadJsonFile(filename)
        if "enabled" not in botConfig: continue
        if botConfig["enabled"]: 
            if "eventId" not in botConfig: continue
            eventId = botConfig["eventId"]
            eventIdhex = utils.normalizeToHex(eventId)
            if eventIdhex is not None:
                enabledBots[npub] = eventIdhex
            else:
                logger.warning("Bot enabled for {npub} but could not convert {eventId} to hex")
    return enabledBots

def getEventByHex(eventHex):
    filters = Filters([Filter(
        event_ids=[eventHex]
    )])
    subscription_id = f"event-{eventHex[0:4]}..{eventHex[-4:]}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    botRelayManager.add_subscription(subscription_id, filters)
    message = json.dumps(request)
    botRelayManager.publish_message(message)
    time.sleep(1)
    eventToReturn = None
    while botRelayManager.message_pool.has_events():
        event_msg = botRelayManager.message_pool.get_event()
        eventToReturn = event_msg.event
    removeSubscription(botRelayManager, subscription_id)
    return eventToReturn

def getResponseEventsForEvent(eventHex, since, until):
    logger.debug(f"Checking for responses to event {eventHex} created from {since} to {until}")
    # filter setup
    filters = Filters([Filter(
        since=since,
        until=until,
        event_refs=[eventHex],
        kinds=[EventKind.TEXT_NOTE]
    )])
    subscription_id = f"refs-{since}-{eventHex[0:4]}..{eventHex[-4:]}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    botRelayManager.add_subscription(subscription_id, filters)
    message = json.dumps(request)
    botRelayManager.publish_message(message)
    time.sleep(1)
    matchingEvents = []
    while botRelayManager.message_pool.has_events():
        event_msg = botRelayManager.message_pool.get_event()
        matchingEvents.append(event_msg.event)
    removeSubscription(botRelayManager, subscription_id)
    return matchingEvents

def getListFieldCount(list, fieldname):
    count = 0
    for item in list:
        if type(item) is dict:
            if fieldname in item:
                count = count + 1
        if isinstance(item, type([])):
            if fieldname in item:
                count = count + 1
    return count

def processEvents(responseEvents, npub, botConfig):
    eventId = botConfig["eventId"]
    feesReplyMessage = 20
    feesZapEvent = 20
    fees = None
    if "fees" in config: fees = config["fees"]
    if fees is not None:
        if "replyMessage" in fees: feesReplyMessage = fees["replyMessage"]
        if "zapEvent" in fees: feesZapEvent = fees["zapEvent"]
    conditions = botConfig["conditions"] if "conditions" in botConfig else []
    excludes = botConfig["excludes"] if "excludes" in botConfig else []
    zapMessage = botConfig["zapMessage"] if "zapMessage" in botConfig else "Thank you!"
    balance = ledger.getCreditBalance(npub)   
    # load existing data
    basePath = f"{files.userEventsFolder}{npub}/{eventId}/"
    utils.makeFolderIfNotExists(basePath)
    fileResponses = f"{basePath}responses.json"
    filePaidNpubs = f"{basePath}paidnpubs.json"
    filePaidLuds = f"{basePath}paidluds.json"
    fileParticipants = f"{basePath}participants.json"
    fileReplies = f"{basePath}replies.json"
    responses = files.loadJsonFile(fileResponses, [])       # event.id
    participants = files.loadJsonFile(fileParticipants, []) # event.public_key
    paidnpubs = files.loadJsonFile(filePaidNpubs, {})       # event.public_key, amount
    paidluds = files.loadJsonFile(filePaidLuds, {})         # lud16, amount
    replies = files.loadJsonFile(fileReplies, [])           # event.id
    randomWinnerCount = getListFieldCount(paidnpubs, "randomWinner")
    # event budget and balance
    eventbudget = botConfig["eventBudget"] if "eventBudget" in botConfig else 0
    if "eventBalance" in botConfig:
        eventbalance = float(botConfig["eventBalance"]) 
    else:
        if eventbudget > 0:
            eventbalance = float(eventbudget) - float(getEventSpentSoFar(npub, eventId))
        else:
            eventbalance = float(balance)
    # tracking
    newest = botConfig["eventSince"]
    # sort chronologically by created_at, (oldest to newest)
    sortedEvents = sorted(responseEvents, key=lambda x: x.created_at)
    # iterate events to find those matching conditions
    candidateEventsToZap = {} # k = evt.id, v = public_key, amount (zapmessage comes later)
    eventsToReply = {}        # k = evt.id, v = public_key, message
    for evt in sortedEvents: #response in sortedEvents:
        #evt = Event(response)
        if not isValidSignature(evt): continue
        created_at = evt.created_at
        pubkey = evt.public_key
        responseId = evt.id
        content = evt.content
        if created_at > newest: newest = created_at
        if getListFieldCount(evt.tags, 'e') != 1: continue # only process top level responses, not nested
        if pubkey in excludes: continue
        if responseId in responses: continue # handled previously, skip
        if pubkey not in participants: participants.append(pubkey)
        # check excludes against content
        excluded = False
        for exclude in excludes:
            if exclude in content: 
                excluded = True
                break
        if excluded: continue
        # check conditions
        foundMessage = False
        foundAmount = False
        foundRandomWinner = False
        for condition in conditions:
            replyMessage = None
            if "replyMessage" not in condition:
                if pubkey in paidnpubs.keys(): continue # paid already, skip
            else:
                replyMessage = condition["replyMessage"]
            if "requiredLength" in condition:
                requiredLength = condition["requiredLength"]
                if len(content) < requiredLength: continue
            if "requiredPhrase" in condition:
                requiredPhrase = condition["requiredPhrase"]
                if str(requiredPhrase).lower() not in str(content).lower(): continue
            if "requiredRegex" in condition:
                requiredRegex = condition["requiredRegex"]
                if not re.search(pattern=requiredRegex, string=content, flags=re.IGNORECASE): continue
            if "randomWinnerLimit" in condition:
                randomWinnerLimit = condition["randomWinnerLimit"]
                if randomWinnerLimit <= randomWinnerCount: continue # hit threshold of this random payout
                oddsimprover = len(paidnpubs) % 100
                random100 = random.randint(1,(100 * (randomWinnerCount + 1)))
                if random100 >= oddsimprover: continue # 1% chance
                foundRandomWinner = True
            # conditional checks passed, now decide actions
            if not foundMessage:
                if replyMessage is not None:
                    if responseId not in eventsToReply.keys():
                        if responseId not in replies:
                            eventsToReply[responseId] = {"public_key": pubkey, "content": replyMessage}
                            foundMessage = True
            if not foundAmount:
                if "amount" in condition:
                    amount = condition["amount"]
                    if amount > 0 and pubkey not in paidnpubs.keys():
                        candidateEventsToZap[responseId] = {"public_key": pubkey, "amount": amount, "replyContent":content, "randomWinner": foundRandomWinner}
                        if foundRandomWinner: randomWinnerCount += 1
                        foundAmount = True
    # save participants so far
    files.saveJsonFile(fileParticipants, participants)
    # reduce eventsToZap to max amount per pubkey in this set
    eventsToZap = {}
    for responseId1, zap1 in candidateEventsToZap.items():
        if responseId1 in eventsToZap.keys(): continue
        zapPubkey = zap1["public_key"]
        zapAmount = zap1["amount"]
        zapRandomWinner = zap1["randomWinner"]
        if not zapRandomWinner:
            for responseId2, zap2 in candidateEventsToZap.items():
                if responseId2 == responseId1: continue
                if zap2["public_key"] == zapPubkey:
                    if zap2["amount"] > zapAmount: 
                        zapAmount = zap2["amount"]
                        zapRandomWinner = zap2["randomWinner"]
        eventsToZap[responseId1] = {"public_key": zapPubkey, "amount": zapAmount, "randomWinner": zapRandomWinner}
    # process reply messages
    pk = PrivateKey().from_nsec(botConfig["profile"]["nsec"])
    for k, v in eventsToReply.items():
        # ensure adequate funds overall
        if balance < 1: break
        # ensure adequate funds for event
        if eventbudget > 0 and eventbalance < (float(feesReplyMessage)/float(1000)): break
        pubkey = v["public_key"]
        if k not in responses: responses.append(k)
        replyTags = [["e", k]]  # eventid being replied to
        replyEvent = Event(content=v["content"],tags=replyTags)
        pk.sign_event(replyEvent)
        botRelayManager.publish_event(replyEvent) # TODO: use localRelayManager
        balance = ledger.recordEntry(npub, "REPLY MESSAGE", 0, -1 * feesReplyMessage, f"Send reply to {pubkey} for {k}")
        eventbalance -= (float(feesReplyMessage)/float(1000))
        replies.append(k)
        files.saveJsonFile(fileReplies, replies)
    # process zaps
    for k, v in eventsToZap.items():
        # k is eventid being replied to
        pubkey = v["public_key"]
        amount = v["amount"]
        amountNeeded = (amount + lnd.config["feeLimit"])
        isRandomWinner = v["randomWinner"]
        # ensure adequate funds overall
        if balance < amountNeeded: continue
        # ensure adequate funds for event
        if eventbudget > 0 and eventbalance < amountNeeded: continue
        if k not in responses: responses.append(k)
        # get lightning id
        lightningId = getLightningIdForPubkey(pubkey)
        if not isValidLightningId(lightningId): continue
        if lightningId in paidluds.keys(): 
            logger.debug(f"Lightning address {lightningId} was already paid for this event")
            continue
        # get callback info and invoice
        lnurlPayInfo, lnurlp = lnurl.getLNURLPayInfo(lightningId)
        callback, bech32lnurl = validateLNURLPayInfo(lnurlPayInfo, lnurlp, lightningId, amount)
        if callback is None or bech32lnurl is None: continue
        logger.debug(f"Preparing zap request for {amount} sats to {lightningId}")
        kind9734 = makeZapRequest(botConfig, amount, zapMessage, pubkey, k, bech32lnurl)
        invoice = lnurl.getInvoiceFromZapRequest(callback, amount, kind9734, bech32lnurl)
        if not lnurl.isValidInvoiceResponse(invoice):
            logger.warning(f"LN Provider of identity {lightningId} did not provide a valid invoice.")
            continue
        verifyUrl = invoice["verify"] if "verify" in invoice else None
        paymentRequest = invoice["pr"]
        decodedInvoice = lnd.decodeInvoice(paymentRequest)
        if not isValidInvoiceAmount(decodedInvoice, amount): 
            logger.warning(f"LN Provider of identity {lightningId} return an unacceptable invoice.")
            continue
        # ok to pay
        paymentTime, paymentTimeISO = utils.getTimes()
        paidnpubs[pubkey] = {"lightning_id":lightningId, "amount_sat": amount, "payment_time": paymentTime, "payment_time_iso": paymentTimeISO, "randomWinner": isRandomWinner}
        paidluds[lightningId] = {"amount_sat": amount, "payment_time": paymentTime, "payment_time_iso": paymentTimeISO}
        if verifyUrl is not None: paidnpubs[pubkey]["payment_verify_url"] = verifyUrl
        balance = ledger.recordEntry(npub, "ZAPS", -1 * amount, 0, f"Zap {lightningId} for reply to {eventId}")
        paymentStatus, paymentFees, paymentHash = lnd.payInvoice(paymentRequest)
        balance = ledger.recordEntry(npub, "ROUTING FEES", 0, -1 * paymentFees, f"Zap {lightningId} for reply to {eventId}")
        balance = ledger.recordEntry(npub, "SERVICE FEES", 0, -1 * feesZapEvent, f"Service fee for zap {lightningId}")
        eventbalance -= float(amount) + (float(paymentFees)/float(1000)) + (float(feesZapEvent)/float(1000))
        paidnpubs[pubkey].update({'payment_status': paymentStatus, 'fee_msat': paymentFees, 'payment_hash': paymentHash})
        # Save responses, paidnpubs, and paidluds after each payment
        files.saveJsonFile(fileResponses, responses)
        files.saveJsonFile(filePaidNpubs, paidnpubs)
        files.saveJsonFile(filePaidLuds, paidluds)
        # Save event balance
        botConfig["eventBalance"] = eventbalance
        setNostrFieldForNpub(npub, "eventBalance", eventbalance)

    # return the created_at value of the most recent event we processed
    return newest

lightningIdCache = {}

def loadLightningIdCache():
    global lightningIdCache
    filename = f"{files.dataFolder}lightningIdcache.json"
    lightningIdCache = files.loadJsonFile(filename, {})

def saveLightningIdCache():
    global lightningIdCache
    filename = f"{files.dataFolder}lightningIdcache.json"
    files.saveJsonFile(filename, lightningIdCache)

def getLightningIdForPubkey(public_key):
    global lightningIdCache
    t, _ = utils.getTimes()
    lightningId = None
    # look in cache for id set within past day
    for k, v in lightningIdCache.items():
        if k != public_key: continue
        if type(v) is dict:
            if "lightningId" not in v: continue
            if "created_at" in v:
                if v["created_at"] > t - 86400:
                    lightningId = v["lightningId"]
                    return lightningId
    # filter setup
    filters = Filters([Filter(kinds=[EventKind.SET_METADATA],authors=[public_key])])
    subscription_id = f"profile-{public_key[0:4]}..{public_key[-4:]}-{t}"
    botRelayManager.add_subscription(subscription_id, filters)
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    message = json.dumps(request)
    botRelayManager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # look over returned events, returning newest lightning Id
    created_at = 0
    while botRelayManager.message_pool.has_events():
        event_msg = botRelayManager.message_pool.get_event()
        try:
            ec = json.loads(event_msg.event.content)
        except Exception as err:
            continue
        if not isValidSignature(event_msg.event): continue
        if event_msg.event.created_at <= created_at: continue
        name = ec["name"] if ("name" in ec and ec["name"] is not None) else "no name"
        if "lud16" in ec and ec["lud16"] is not None: 
            lightningId = ec["lud16"]
            created_at = event_msg.event.created_at
            lightningIdCache[public_key] = {"lightningId": lightningId, "name":name, "created_at": created_at}
    removeSubscription(botRelayManager, subscription_id)
    if lightningId is not None: saveLightningIdCache()
    return lightningId

def isValidLightningId(lightningId):
    if lightningId is None:
        logger.debug(f"No lightning address")
        return False
    identityParts = lightningId.split("@")
    if len(identityParts) != 2: 
        logger.debug(f"Lightning address {lightningId} is invalid - not in username@domain format")
        return False
    return True

def validateLNURLPayInfo(lnurlPayInfo, lnurlp, lightningId, amount):
    callback = None
    bech32lnurl = None
    if lnurlPayInfo is None:
        logger.warning(f"Could not get LNURL info for address: {lightningId}")
        return callback, bech32lnurl
    if lnurlp is None:
        logger.debug(f"Lightning address {lightningId} is invalid - not in username@domain format")
        return callback, bech32lnurl
    if "allowsNostr" not in lnurlPayInfo:
        logger.debug(f"LN Provider of identity {lightningId} does not support nostr. Zap not supported")
        return callback, bech32lnurl
    if not lnurlPayInfo["allowsNostr"]:
        logger.debug(f"LN Provider of identity {lightningId} does not allow nostr. Zap not supported")
        return callback, bech32lnurl
    if "nostrPubkey" not in lnurlPayInfo:
        logger.warning(f"LN Provider of identity {lightningId} does not have nostrPubkey. Publisher of receipt could be anyone")
    if not all(k in lnurlPayInfo for k in ("callback","minSendable","maxSendable")): 
        logger.debug(f"LN Provider of identity {lightningId} does not have proper callback, minSendable, or maxSendable info. Zap not supported")
        return callback, bech32lnurl
    minSendable = lnurlPayInfo["minSendable"]
    maxSendable = lnurlPayInfo["maxSendable"]
    if (amount * 1000) < minSendable:
        logger.debug(f"LN Provider of identity {lightningId} does not allow zaps less than {minSendable} msat. Skipping")
        return callback, bech32lnurl
    if (amount * 1000) > maxSendable:
        logger.debug(f"LN Provider of identity {lightningId} does not allow zaps greater than {maxSendable} msat. Skipping")
        return callback, bech32lnurl
    callback = lnurlPayInfo["callback"]
    lnurlpBytes = bytes(lnurlp,'utf-8')
    lnurlpBits = bech32.convertbits(lnurlpBytes,8,5)
    bech32lnurl = bech32.bech32_encode("lnurl", lnurlpBits)
    return callback, bech32lnurl

def makeZapRequest(botConfig, amountToZap, zapMessage, recipientPubkey, eventId, bech32lnurl):
    pk = PrivateKey().from_nsec(botConfig["profile"]["nsec"])
    amountMillisatoshi = amountToZap*1000
    zapTags = []    
    relaysTagList = []
    relaysTagList.append("relays")
    relays = []
    botrelays = botConfig["relays"] if "relays" in botConfig else config["relays"]
    for relay in botrelays:
        if type(relay) is str:
            relays.append(relay)
        if type(relay) is dict:
            canread = relay["read"] if "read" in relay else True
            if canread and "url" in relay: relays.append(relay["url"])
    relaysTagList.extend(relays)
    zapTags.append(relaysTagList)
    zapTags.append(["amount", str(amountMillisatoshi)])
    zapTags.append(["lnurl", bech32lnurl])
    zapTags.append(["p",recipientPubkey])
    zapTags.append(["e",eventId])
    zapEvent = Event(content=zapMessage,kind=9734,tags=zapTags)
    pk.sign_event(zapEvent)
    return zapEvent

def isValidInvoiceAmount(decodedInvoice, amountToZap):
    logger.debug(f"Checking if invoice is valid")
    amountMillisatoshi = amountToZap*1000
    if not all(k in decodedInvoice for k in ("num_satoshis","num_msat")): 
        logger.warning(f"Invoice did not set amount")
        return False
    num_satoshis = int(decodedInvoice["num_satoshis"])
    if num_satoshis != amountToZap:
        logger.warning(f"Invoice amount ({num_satoshis}) does not match requested amount ({amountToZap}) to zap")
        return False
    num_msat = int(decodedInvoice["num_msat"])
    if num_msat != amountMillisatoshi:
        logger.warning(f"Invoice amount of msats ({num_msat}) does not match requested amount ({amountMillisatoshi}) to zap")
        return False
    return True

def processOutstandingPayments(npub, botConfig):
    eventId = botConfig["eventId"]
    basePath = f"{files.userEventsFolder}{npub}.{eventId}."
    filePaidNpubs = f"{basePath}paidnpubs.json"
    paidnpubs = files.loadJsonFile(filePaidNpubs, {})       # event.public_key, amount
    for paidnpub, paidentry in paidnpubs.items():
        if "payment_status" not in paidentry: continue
        if "payment_hash" not in paidentry: continue
        payment_status = paidentry["payment_status"]
        original_fee_msat = 0
        if payment_status in ("IN_FLIGHT","TIMEOUT","UNKNOWNPAYING","UNKNOWNTRACKING","NOTFOUND"):
            if "fee_msat" in paidentry: original_fee_msat = paidentry["fee_msat"]
            payment_hash = paidentry["payment_hash"]
            lightningId = ""
            if "lightning_id" in paidentry: lightningId = paidentry["lightning_id"]
            logger.info(f"Tracking LND payment with payment_hash {payment_hash} for {lightningId} - {paidnpub}")
            payment_status, fee_msat = lnd.trackPayment(payment_hash)
            if payment_status is None: continue
            if payment_status == "TIMEOUT": continue
            if fee_msat is None: continue
            paidnpubs[paidnpub]["payment_status"] = payment_status
            paidnpubs[paidnpub]["fee_msat"] = fee_msat
            files.saveJsonFile(filePaidNpubs, paidnpubs)
            if fee_msat > original_fee_msat:
                # additional fee? should never happen
                additionalFee = fee_msat - original_fee_msat
                balance = ledger.recordEntry(npub, "ROUTING FEES", 0, -1 * additionalFee, f"Zap {lightningId} for reply to {eventId}")
            elif fee_msat < original_fee_msat:
                # credit
                creditForFee = original_fee_msat - fee_msat
                balance = ledger.recordEntry(npub, "ROUTING FEES", 0, creditForFee, f"Credit for zap payment after routing fee finalized for {lightningId} for reply to {eventId}")

