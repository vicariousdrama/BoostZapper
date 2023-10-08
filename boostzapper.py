#!/usr/bin/env python3

from os.path import exists
from urllib3.exceptions import InsecureRequestWarning, ReadTimeoutError
from nostr.key import PrivateKey, PublicKey
from nostr.event import Event, EventKind
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
from nostr.relay_manager import RelayManager
import bech32
import json
import logging
import math
import os
import requests
import ssl
import sys
import time
import urllib.parse

def getConfig(filename):
    logger.debug(f"Loading config from {filename}")
    if not exists(filename):
        logger.warn(f"Config file does not exist at {filename}")
        return {}
    with open(filename) as f:
        return(json.load(f))

def validateConfig(config):
    hasErrors = False
    if "zapConditions" not in config:
        logger.error("Configuration is missing zapConditions")
        hasErrors = True
    else:
        zc = 0
        for zapCondition in config["zapConditions"]:
            zc += 1
            if "zapAmount" not in zapCondition:
                logger.error(f"zapCondition # {zc} in configuration is missing zapAmount")
                hasErrors = True
    if "lndServer" not in config:
        logger.error("Configuration is missing lndServer")
        hasErrors = True
    else:
        if "address" not in config["lndServer"]:
            logger.error("Configuration file is missing address in lndServer")
            hasErrors = True
        if "port" not in config["lndServer"]:
            logger.error("Configuration file is missing port in lndServer")
            hasErrors = True
        if "macaroon" not in config["lndServer"]:
            logger.error("Configuration file is missing macaroon in lndServer")
            hasErrors = True
        if "paymentTimeout" not in config["lndServer"]:
            logger.error("Configuration file is missing paymentTimeout in lndServer")
            hasErrors = True
        if "feeLimit" not in config["lndServer"]:
            logger.error("Configuration file is missing feeLimit in lndServer")
            hasErrors = True
    if hasErrors: quit()

def getPubkeyListFilename(listName, eventId):
    return f"data/{eventId}.{listName}.json"

def loadPubkeys(listName, eventId):
    filename = getPubkeyListFilename(listName, eventId)
    if not exists(filename): return []
    with open(filename) as f:
        return(json.load(f))

def savePubkeys(listName, eventId, d):
    filename = getPubkeyListFilename(listName, eventId)
    with open(filename, "w") as f:
        f.write(json.dumps(obj=d,indent=2))

def loadLud16Cache():
    filename = "data/lud16cache.json"
    if not exists(filename): return {}
    with open(filename) as f:
        return(json.load(f))

def saveLud16Cache(d):
    filename = "data/lud16cache.json"
    with open(filename, "w") as f:
        f.write(json.dumps(obj=d,indent=2))

def getNostrRelays(d, k):
    if k in d: return d[k]
    logger.warn("Using default relays as none were defined")
    return ["nostr.pleb.network",
            "nostr-pub.wellorder.net",
            "nostr.mom",
            "relay.nostr.bg"
            ]

def getZapMessage(d, k):
    if k in d: return d[k]
    return "Zap!"

def getEventId(d, k):
    if k in d: return d[k]
    logger.error(f"Required field {k} not found. Check configuration")
    quit()

def getExcludePubkeys(d, k):
    if k in d: return d[k]
    return []

def normalizePubkeys(d):
    z = []
    for n in d:
        if str(n).startswith("npub"):
            z.append(PublicKey().from_npub(n).hex())
        else:
            z.append(n)
    return z

def getPrivateKey(d, k):
    if k not in d:
        logger.warn(f"{k} not defined. A new one will be created")
        return PrivateKey() # generate new each time script run
    v = d[k]
    if v == None:
        logger.warn(f"{k} is empty. A new one will be created")
        return PrivateKey() # generate new each time script run
    if len(v) == 64: # assumes in hex format
        raw_secret = bytes.fromhex(v)
        return PrivateKey(raw_secret=raw_secret)
    if str(v).startswith("nsec"): # in user friendly nsec bech32
        return PrivateKey().from_nsec(v)
    logger.warn(f"{k} is not in nsec or hex format. A new one will be created")
    return PrivateKey()

def isValidSignature(event):
    sig = event.signature
    id = event.id
    publisherPubkey = event.public_key
    pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey))
    return pubkey.verify_signed_message_hash(hash=id, sig=sig)

def getEventsOfEvent(eventId, relays):
    # filter setup
    t=int(time.time())
    filters = Filters([Filter(event_refs=[eventId],kinds=[EventKind.TEXT_NOTE])])
    subscription_id = f"events-of-{eventId[0:4]}..{eventId[-4:]}-{t}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    # connect to relays
    relay_manager = RelayManager()
    for nostrRelay in relays:
        relay_manager.add_relay(f"wss://{nostrRelay}")
    relay_manager.add_subscription(subscription_id, filters)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    time.sleep(1.25) # allow the connections to open
    # push request to relays
    message = json.dumps(request)
    relay_manager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # wait for events to return, gather and close
    matchingEvents = []
    while relay_manager.message_pool.has_events():
        event_msg = relay_manager.message_pool.get_event()
        matchingEvents.append(event_msg)
    relay_manager.close_connections()
    # return them
    return matchingEvents

def lookupLud16ForPubkey(userPubkey):
    lud16 = None
    # filter setup
    filters = Filters([Filter(kinds=[EventKind.SET_METADATA],authors=[userPubkey])])
    t=int(time.time())
    subscription_id = f"profile-{userPubkey[0:4]}..{userPubkey[-4:]}-{t}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    # connect to relays
    relay_manager = RelayManager()
    for nostrRelay in relays:
        relay_manager.add_relay(f"wss://{nostrRelay}")
    relay_manager.add_subscription(subscription_id, filters)
    relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) # NOTE: This disables ssl certificate verification
    time.sleep(1.25) # allow the connections to open
    # push request to relays
    message = json.dumps(request)
    relay_manager.publish_message(message)
    time.sleep(1) # allow the messages to send
    # look over returned events
    while relay_manager.message_pool.has_events():
        event_msg = relay_manager.message_pool.get_event()
        if lud16 is not None: continue
        try:
            ec = json.loads(event_msg.event.content)
        except Exception as err:
            continue
        if not isValidSignature(event_msg.event): 
            continue
        if "lud16" in ec and ec["lud16"] is not None: 
            lud16 = ec["lud16"]
    relay_manager.close_connections()
    return lud16

def gettimeouts():
    return (5,30)

def gettorproxies():
    # with tor service installed, default port is 9050
    # to find the port to use, can run the following
    #     cat /etc/tor/torrc | grep SOCKSPort | grep -v "#" | awk '{print $2}'
    return {'http': 'socks5h://127.0.0.1:9050','https': 'socks5h://127.0.0.1:9050'}

def geturl(useTor=True, url=None, defaultResponse="{}", headers={}):
    try:
        proxies = gettorproxies() if useTor else {}
        timeout = gettimeouts()
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
        resp = requests.get(url,timeout=timeout,allow_redirects=True,proxies=proxies,headers=headers,verify=False)
        cmdoutput = resp.text
        return json.loads(cmdoutput)
    except Exception as e:
        return json.loads(defaultResponse)

def getLNURLPayInfo(identity):
    identityParts = identity.split("@")
    if len(identityParts) != 2: 
        return None, None
    username = identityParts[0]
    domainname = identityParts[1]
    useTor = False
    protocol = "https"
    if domainname.endswith(".onion"): 
        protocol = "http"
        useTor = True
    url = f"{protocol}://{domainname}/.well-known/lnurlp/{username}"
    j = geturl(useTor, url)
    return j, url

def makeZapRequest(satsToZap, zapMessage, recipientPubkey, eventId, bech32lnurl):
    global relays
    amountMillisatoshi = satsToZap*1000
    zapTags = []
    zapTags.append(["relays", relays])
    zapTags.append(["amount", str(amountMillisatoshi)])
    zapTags.append(["lnurl", bech32lnurl])
    zapTags.append(["p",recipientPubkey])
    zapTags.append(["e",eventId])
    zapEvent = Event(content=zapMessage,kind=9734,tags=zapTags)
    botKey.sign_event(zapEvent)
    return zapEvent

def getInvoiceFromZapRequest(callback, satsToZap, zapRequest, bech32lnurl):
    jd = zapRequest.to_message()
    jd = jd[10:len(jd)-1]       # removes ["EVENT", ] envelope
    encoded = urllib.parse.quote(jd)
    amountMillisatoshi = satsToZap*1000
    useTor = False
    if ".onion" in callback: useTor = True
    if "?" in callback:
        url = f"{callback}&"
    else:
        url = f"{callback}?"
    url = f"{url}amount={amountMillisatoshi}&nostr={encoded}&lnurl={bech32lnurl}"
    logger.debug(f"zap request url: {url}")
    j = geturl(useTor, url)
    return j

def isValidInvoiceResponse(invoiceResponse):
    if "status" in invoiceResponse:
        if invoiceResponse["status"] == "ERROR":
            errReason = "unreported reason"
            if "reason" in invoiceResponse: errReason = invoiceResponse["reason"]
            logger.warn(f"Invoice request error: {errReason}")
            return False
    if "pr" not in invoiceResponse: return False
    return True

def getDecodedInvoice(paymentRequest, lndServer):
    serverAddress = lndServer["address"]
    serverPort = lndServer["port"]
    lndCallSuffix = f"/v1/payreq/{paymentRequest}"
    url = f"https://{serverAddress}:{serverPort}{lndCallSuffix}"
    useTor = False
    if ".onion" in serverAddress: useTor = True
    headers = {"Grpc-Metadata-macaroon": lndServer["macaroon"]}
    j = geturl(useTor=useTor, url=url, headers=headers)
    return j

def isValidInvoice(decodedInvoice, satsToZap):
    amountMillisatoshi = satsToZap*1000
    if not all(k in decodedInvoice for k in ("num_satoshis","num_msat")): 
        logger.warn(f"Invoice did not set amount")
        return False
    num_satoshis = int(decodedInvoice["num_satoshis"])
    if num_satoshis != satsToZap:
        logger.warn(f"Invoice amount ({num_satoshis}) does not match requested amount ({satsToZap}) to zap")
        return False
    num_msat = int(decodedInvoice["num_msat"])
    if num_msat != amountMillisatoshi:
        logger.warn(f"Invoice amount of msats ({num_msat}) does not match requested amount ({amountMillisatoshi}) to zap")
        return False
    return True

def payInvoice(paymentRequest, lndServer):
    feeLimit = lndServer["feeLimit"]
    paymentTimeout = lndServer["paymentTimeout"]
    serverAddress = lndServer["address"]
    serverPort = lndServer["port"]
    lndCallSuffix = "/v2/router/send"
    url = f"https://{serverAddress}:{serverPort}{lndCallSuffix}"
    lndPostData = {
        "payment_request": paymentRequest,
        "fee_limit_sat": feeLimit,
        "timeout_seconds": paymentTimeout
    }
    proxies = gettorproxies() if ".onion" in serverAddress else {}
    timeout = gettimeouts()
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    resultStatus = "UNKNOWN"
    resultFeeMSat = 0
    headers = {"Grpc-Metadata-macaroon": lndServer["macaroon"]}
    headers["Connection"] = "close"
    r = requests.post(url=url,stream=True,data=json.dumps(lndPostData),timeout=timeout,proxies=proxies,headers=headers,verify=False)
    try:
        for raw_response in r.iter_lines():
            json_response = json.loads(raw_response)
            if "result" not in json_response:
                logger.warn(f" - unexpected stream response format")
                logger.warn(f"   {json_response}")
            else:
                newStatus = resultStatus
                if "status" in json_response["result"]:
                    newStatus = json_response["result"]["status"]
                if "fee_msat" in json_response["result"]:
                    resultFeeMSat = int(json_response["result"]["fee_msat"])
                if newStatus != resultStatus:
                    resultStatus = newStatus
                    if resultStatus == "SUCCEEDED":
                        logger.info(f" - {resultStatus}, fee paid: {resultFeeMSat} msat")
                    elif resultStatus == "FAILED":
                        failureReason = "unknown failure reason"
                        if "failure_reason" in json_response["result"]:
                            failureReason = json_response["result"]["failure_reason"]
                        logger.warn(f" - {resultStatus} : {failureReason}")
                    elif resultStatus == "IN_FLIGHT":
                        logger.debug(f" - {resultStatus}")
                    else:
                        logger.info(f" - {resultStatus}")
                        logger.info(json_response)
    except ReadTimeoutError as rte:
        try:
            r.close()
        except Exception as e:
            pass
        return "TIMEOUT", (feeLimit * 1000)
    r.close()
    return resultStatus, resultFeeMSat


# Logging to systemd
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Global config
config = getConfig("config.json")

if __name__ == '__main__':

    if not exists("data/"):
        os.makedirs("data/")

    # Read in key config info
    eventId = getEventId(config, "referencedEventId")       # TODO: convert to command arg
    if str(eventId).startswith("nostr:"): eventId = eventId[6:]
    if str(eventId).startswith("nevent"):
        e1, e2 = bech32.bech32_decode(eventId)
        tlv_bytes = bech32.convertbits(e2, 5, 8)[:-1]
        tlv_length = tlv_bytes[1]
        tlv_value = tlv_bytes[2:tlv_length+2]
        eventId = bytes(tlv_value).hex()
    botKey = getPrivateKey(config, "botPrivateKey")
    relays = getNostrRelays(config, "relays")
    excludePubkeys = normalizePubkeys(getExcludePubkeys(config, "excludePubkeys"))
    validateConfig(config)
    zapConditions = config["zapConditions"]
    zapMessage = getZapMessage(config, "zapMessage")
    conditionCounter = len(zapConditions)

    # Pubkey to LUD16 cache
    lud16PubkeyCache = loadLud16Cache()

    # Load existing from tracking files
    participantPubkeys = loadPubkeys("participants", eventId)
    paidPubkeys = loadPubkeys("paid", eventId)
    paidLuds = loadPubkeys("paidluds", eventId)
    unzappablePubkeys = []

    # Get Nostr Events referencing the event
    foundEvents = getEventsOfEvent(eventId, relays)

    # Metrics tracking
    totalSatsPaid = 0
    totalFeesPaid = 0
    statusCounts = {"PAYMENTATTEMPTS": 0, "SKIPPED":0}

    # Check the events that others posted
    for msgEvent in foundEvents:
        logger.debug("-" * 60)
        if not isValidSignature(msgEvent.event):
            logger.warning(f"Event has invalid signature, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        publisherPubkey = msgEvent.event.public_key
        bech32Pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey)).bech32()
        publisherEventId = msgEvent.event.id
        eventContent = msgEvent.event.content
        logger.debug(f"Reviewing event")
        logger.debug(f" - id     : {publisherEventId}")
        logger.debug(f" - pubkey : {publisherPubkey}")
        logger.debug(f" - content: {eventContent}")
        # check if pubkey on exclusion list
        if publisherPubkey in excludePubkeys:
            logger.debug(f"User is on exclusion list, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # skip any already paid
        if publisherPubkey in paidPubkeys: 
            logger.debug(f"User was already paid for this event, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # add to participants if not yet present
        if publisherPubkey not in participantPubkeys:
            participantPubkeys.append(publisherPubkey)
        # check conditions
        conditionFound = False
        conditionNumber = 0
        satsToZap = 0
        while not conditionFound and conditionNumber < conditionCounter:
            zapCondition = zapConditions[conditionNumber]
            conditionNumber += 1
            if "requiredLength" in zapCondition:
                if zapCondition["requiredLength"] > len(eventContent):
                    continue
            if "requiredPhrase" in zapCondition:
                if zapCondition["requiredPhrase"] is not None:
                    if str(zapCondition["requiredPhrase"]).lower() not in str(eventContent).lower():
                        continue
            conditionFound = True
            satsToZap = zapCondition["zapAmount"]
            logger.debug(f"Conditions matched. Planning to zap {satsToZap} sats")
        # We have amount to be zapped if condition was found
        if not conditionFound: 
            logger.debug(f"Content from {publisherPubkey} didnt meet zap conditions, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # Get LUD16 for user
        if publisherPubkey in lud16PubkeyCache:
            lud16 = lud16PubkeyCache[publisherPubkey]
        else:
            lud16 = lookupLud16ForPubkey(publisherPubkey)
            if lud16 is None:
                logger.info(f"Unable to zap user. No lightning address found in profile, skipping")
                if publisherPubkey not in unzappablePubkeys:
                    unzappablePubkeys.append(publisherPubkey)
                statusCounts["SKIPPED"] += 1
                continue
            lud16PubkeyCache[publisherPubkey] = lud16
            saveLud16Cache(lud16PubkeyCache)
        logger.debug(f" - lud16  : {lud16}")
        # Check if we've already paid this lightning user
        if lud16 in paidLuds: 
            logger.debug(f"Lightning address for User {lud16} was already paid for this event, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # Get lnurlpay info
        lnurlPayInfo, lnurl = getLNURLPayInfo(lud16)
        lnurlBytes = bytes(lnurl,'utf-8')
        lnurlBits = bech32.convertbits(lnurlBytes,8,5)
        bech32lnurl = bech32.bech32_encode("lnurl", lnurlBits)
        if lnurlPayInfo is None:
            logger.warn(f"Could not get LNURL info for identity: {lud16}. skipped")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        ## these next few fields are enforcing nostr and zaps. this is an extension
        ## of lnurlp and we could still request and pay an invoice directly that
        ## doesnt involve nostr without that, but since we want to reward promotions
        ## within nostr, i'll leave these in
        if "allowsNostr" not in lnurlPayInfo:
            logger.debug(f"LN Provider of identity {lud16} does not support nostr. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        if not lnurlPayInfo["allowsNostr"]:
            logger.debug(f"LN Provider of identity {lud16} does not allow nostr. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        ## this one is the payment providers pubkey which we (and others) can use to
        ## validate the zap receipt that the provider will publish to nostr
        if "nostrPubkey" not in lnurlPayInfo:
            logger.debug(f"LN Provider of identity {lud16} does not have nostrPubkey. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        nostrPubkey = lnurlPayInfo["nostrPubkey"]
        if not all(k in lnurlPayInfo for k in ("callback","minSendable","maxSendable")): 
            logger.debug(f"LN Provider of identity {lud16} does not have proper callback, minSendable, or maxSendable info. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        ## these ones must be present to be valid
        callback = lnurlPayInfo["callback"]
        minSendable = lnurlPayInfo["minSendable"]
        maxSendable = lnurlPayInfo["maxSendable"]
        # check amount within range (minSendable and maxSendable are in millisats)
        if (satsToZap * 1000) < minSendable:
            logger.debug(f"LN Provider of identity {lud16} does not allow zaps less than {minSendable} msat. Skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        if (satsToZap * 1000) > maxSendable:
            logger.debug(f"LN Provider of identity {lud16} does not allow zaps greater than {maxSendable} msat. Skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # prepare and sign kind9734 request
        kind9734 = makeZapRequest(satsToZap, zapMessage, publisherPubkey, publisherEventId, bech32lnurl)
        # send to provider, requesting invoice
        invoice = getInvoiceFromZapRequest(callback, satsToZap, kind9734, bech32lnurl)
        if not isValidInvoiceResponse(invoice):
            logger.debug(f"Response from LN Provider of identity {lud16} did not provide a valid invoice. skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # Decode it
        paymentRequest = invoice["pr"]
        decodedInvoice = getDecodedInvoice(paymentRequest, config["lndServer"])
        # check if within ranges
        if not isValidInvoice(decodedInvoice, satsToZap):
            logger.warn(f"Invoice from LN Provider of identity {lud16} is unacceptable. skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # ok. If we got this far, we can pay it
        paidPubkeys.append(publisherPubkey)
        paidLuds.append(lud16)
        statusCounts["PAYMENTATTEMPTS"] += 1
        logger.debug(f"Attempting payment of invoice")
        paymentStatus, paymentFees = payInvoice(paymentRequest, config["lndServer"])
        logger.debug(f"Payment complete...{paymentStatus}, fees paid: {paymentFees}")
        if paymentStatus == "SUCCEEDED":
            totalFeesPaid += paymentFees
        totalSatsPaid += satsToZap
        if paymentStatus in statusCounts:
            statusCounts[paymentStatus] = statusCounts[paymentStatus] + 1
        else:
            statusCounts[paymentStatus] = 1
        # Save our paid every round
        savePubkeys("paid", eventId, paidPubkeys)
        savePubkeys("paidluds", eventId, paidLuds)

    # Save data at end
    savePubkeys("participants", eventId, participantPubkeys)

    # Report unzappable
    if len(unzappablePubkeys) > 0:
        logger.info("-" * 60)
        logger.info("Unzappable npubs:")
        for p in unzappablePubkeys:
            npub = PublicKey(raw_bytes=bytes.fromhex(p)).bech32()
            logger.info(f"  {npub}")

    # Report status counts
    logger.info("-" * 60)
    feesAsSats = int(math.ceil(float(totalFeesPaid)/float(1000)))
    for k in statusCounts.keys():
        logger.info(f"{k} = {statusCounts[k]}")
    logger.info(f"Sats paid: {totalSatsPaid} sats")
    logger.info(f"Fees paid: {totalFeesPaid} msats")
    logger.info( "--------------------------")
    logger.info(f"Total    : {totalSatsPaid + feesAsSats} sats")
