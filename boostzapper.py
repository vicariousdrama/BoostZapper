#!/usr/bin/env python3
from datetime import datetime
from os.path import exists
from urllib3.exceptions import InsecureRequestWarning, ReadTimeoutError
from nostr.key import PrivateKey, PublicKey
from nostr.event import Event, EventKind
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
from nostr.relay_manager import RelayManager
import base64
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

# Crude command line parsing. p is a parameter name for which
# a value is saught. If p is found, then the next arg is the
# value for p.
def getCommandArg(p):
    b = False
    v = None
    l = str(p).lower()
    for a in sys.argv:
        if b:
            v = a
            b = False
        elif f"--{l}" == str(a).lower():
            b = True
    return v

def getConfig(filename):
    c = getCommandArg("config") # allow overriding default filename
    if c is not None: filename = c
    logger.debug(f"Loading config from {filename}")
    if not exists(filename):
        logger.warning(f"Config file does not exist at {filename}")
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
        for k in ("address","port","macaroon","paymentTimeout","feeLimit"):
            if k not in config["lndServer"]:
                logger.error(f"Configuration file is missing {k} in lndServer")
                hasErrors = True
    if hasErrors: quit()

def getPubkeyListFilename(listName, eventId):
    return f"{dataFolder}{eventId}.{listName}.json"

def loadPubkeys(listName, eventId):
    filename = getPubkeyListFilename(listName, eventId)
    if not exists(filename): return []
    with open(filename) as f:
        return(json.load(f))

def savePubkeys(listName, eventId, d):
    filename = getPubkeyListFilename(listName, eventId)
    with open(filename, "w") as f:
        f.write(json.dumps(obj=d,indent=2))

def listtodict(o):
    if type(o) is dict: return o
    if type(o) is list:
        d = {}
        for v in o:
            d[v] = {}
        return d

def getPubkey2LightningCacheFilename():
    return f"{dataFolder}lightningIdcache1.json"

def loadPubkey2LightningCache():
    filename = getPubkey2LightningCacheFilename()
    if not exists(filename): return {}
    with open(filename) as f:
        return(json.load(f))

def savePubkey2LightningCache(d):
    filename = getPubkey2LightningCacheFilename()
    with open(filename, "w") as f:
        f.write(json.dumps(obj=d,indent=2))

def getNostrRelays(d, k):
    if k in d: return d[k]
    logger.warning("Using default relays as none were defined")
    return ["nostr.pleb.network",
            "nostr-pub.wellorder.net",
            "nostr.mom",
            "relay.nostr.bg"
            ]

def getZapMessage(d, k):
    c = getCommandArg("zapMessage") # allow overriding config from args
    if c is not None: return c
    if k in d: return d[k]
    return "Zap!"

def getEventId(d, k):
    c = getCommandArg("referencedEventId") # allow overriding config from args
    if c is not None: return c
    if k in d: return d[k]
    logger.error(f"Required field {k} not found. Check configuration")
    quit()

def getExcludePubkeys(d, k):
    if k in d: return d[k]
    return []

def getExcludeContent(d, k):
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
    thePrivateKey = None
    if k not in d:
        logger.warning(f"{k} not defined. A new one will be created")
    else:        
        v = d[k]
        if v == None:
            logger.warning(f"{k} is empty. A new one will be created")
        elif len(v) == 64: # assumes in hex format
            raw_secret = bytes.fromhex(v)
            thePrivateKey = PrivateKey(raw_secret=raw_secret)
        elif str(v).startswith("nsec"): # in user friendly nsec bech32
            thePrivateKey = PrivateKey().from_nsec(v)
        else:
            logger.warning(f"{k} is not in nsec or hex format. A new one will be created")
    if thePrivateKey is None:
        # generate and report
        thePrivateKey = PrivateKey()
        logger.info(f"The new private key created is")
        logger.info(f"   {thePrivateKey.bech32()}")
        logger.info(f"   {thePrivateKey.hex()}")
    return thePrivateKey

def isValidSignature(event):
    sig = event.signature
    id = event.id
    publisherPubkey = event.public_key
    pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey))
    return pubkey.verify_signed_message_hash(hash=id, sig=sig)

def getEventsOfEvent(eventId, relays):
    logger.debug(f"Retreiving events from relays that are referencing the event")
    # filter setup
    t=int(time.time())
    filters = Filters([Filter(event_refs=[eventId],kinds=[EventKind.TEXT_NOTE])])
    subscription_id = f"events-of-{eventId[0:4]}..{eventId[-4:]}-{t}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    # connect to relays
    relay_manager = RelayManager()
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
    matchingEvents = []
    while relay_manager.message_pool.has_events():
        event_msg = relay_manager.message_pool.get_event()
        matchingEvents.append(event_msg)
    relay_manager.close_connections()
    # return them
    return matchingEvents

def getLightningIdForPubkey(userPubkey):
    lightningId = None
    # filter setup
    filters = Filters([Filter(kinds=[EventKind.SET_METADATA],authors=[userPubkey])])
    t=int(time.time())
    subscription_id = f"profile-{userPubkey[0:4]}..{userPubkey[-4:]}-{t}"
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    # connect to relays
    relay_manager = RelayManager()
    for nostrRelay in relays:
        relay_manager.add_relay(nostrRelay)
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
        if lightningId is not None: continue
        try:
            ec = json.loads(event_msg.event.content)
        except Exception as err:
            continue
        if not isValidSignature(event_msg.event): 
            continue
        if "lud16" in ec and ec["lud16"] is not None: 
            lightningId = ec["lud16"]
    relay_manager.close_connections()
    return lightningId

def gettimeouts():
    return (5,30) # connect, read in seconds  TODO: make configurable?

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
    relaysTagList = []
    relaysTagList.append("relays")
    relaysTagList.extend(relays)
    zapTags.append(relaysTagList)
    zapTags.append(["amount", str(amountMillisatoshi)])
    zapTags.append(["lnurl", bech32lnurl])
    zapTags.append(["p",recipientPubkey])
    zapTags.append(["e",eventId])
    zapEvent = Event(content=zapMessage,kind=9734,tags=zapTags)
    botKey.sign_event(zapEvent)
    return zapEvent

def getEncodedZapRequest(zapRequest):
    o = {
            "id": zapRequest.id,
            "pubkey": zapRequest.public_key,
            "created_at": zapRequest.created_at,
            "kind": zapRequest.kind,
            "tags": zapRequest.tags,
            "content": zapRequest.content,
            "sig": zapRequest.signature,
        }
    jd = json.dumps(o)
    encoded = urllib.parse.quote(jd)
    return encoded

def getInvoiceFromZapRequest(callback, satsToZap, zapRequest, bech32lnurl):
    logger.debug(f"Requesting invoice from LNURL service using zap request")
    encoded = getEncodedZapRequest(zapRequest)
    amountMillisatoshi = satsToZap*1000
    useTor = False
    if ".onion" in callback: useTor = True
    if "?" in callback:
        url = f"{callback}&"
    else:
        url = f"{callback}?"
    url = f"{url}amount={amountMillisatoshi}&nostr={encoded}&lnurl={bech32lnurl}"
    #logger.debug(f"zap request url: {url}")    # for debugging relays
    j = geturl(useTor, url)
    return j

def isValidInvoiceResponse(invoiceResponse):
    if "status" in invoiceResponse:
        if invoiceResponse["status"] == "ERROR":
            errReason = "unreported reason"
            if "reason" in invoiceResponse: errReason = invoiceResponse["reason"]
            logger.warning(f"Invoice request error: {errReason}")
            return False
    if "pr" not in invoiceResponse: return False
    return True

def getDecodedInvoice(paymentRequest, lndServer):
    logger.debug(f"Decoding invoice")
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
    logger.debug(f"Checking if invoice is valid")
    amountMillisatoshi = satsToZap*1000
    if not all(k in decodedInvoice for k in ("num_satoshis","num_msat")): 
        logger.warning(f"Invoice did not set amount")
        return False
    num_satoshis = int(decodedInvoice["num_satoshis"])
    if num_satoshis != satsToZap:
        logger.warning(f"Invoice amount ({num_satoshis}) does not match requested amount ({satsToZap}) to zap")
        return False
    num_msat = int(decodedInvoice["num_msat"])
    if num_msat != amountMillisatoshi:
        logger.warning(f"Invoice amount of msats ({num_msat}) does not match requested amount ({amountMillisatoshi}) to zap")
        return False
    return True

def payInvoice(paymentRequest, lndServer):
    logger.debug(f"Paying invoice")
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
    resultStatus = "UNKNOWNPAYING"
    resultFeeMSat = 0
    headers = {"Grpc-Metadata-macaroon": lndServer["macaroon"]}
    headers["Connection"] = "close"
    json_response = None
    payment_hash = None
    r = requests.post(url=url,stream=True,data=json.dumps(lndPostData),timeout=timeout,proxies=proxies,headers=headers,verify=False)
    try:
        for raw_response in r.iter_lines():
            json_response = json.loads(raw_response)
            if "result" in json_response: json_response = json_response["result"]
            newStatus = resultStatus
            if "status" in json_response:
                newStatus = json_response["status"]
            if "fee_msat" in json_response:
                resultFeeMSat = int(json_response["fee_msat"])
            if "payment_hash" in json_response:
                payment_hash = json_response["payment_hash"]
            if newStatus != resultStatus:
                resultStatus = newStatus
                if resultStatus == "SUCCEEDED":
                    logger.debug(f" - {resultStatus}, routing fee paid: {resultFeeMSat} msat")
                elif resultStatus == "FAILED":
                    failureReason = "unknown failure reason"
                    if "failure_reason" in json_response:
                        failureReason = json_response["failure_reason"]
                    logger.warning(f" - {resultStatus} : {failureReason}")
                elif resultStatus == "IN_FLIGHT":
                    logger.debug(f" - {resultStatus}")
                else:
                    logger.info(f" - {resultStatus}")
                    logger.info(json_response)
    except Exception as rte: # (ConnectionError, TimeoutError, ReadTimeoutError) as rte:
        try:
            r.close()
        except Exception as e:
            logger.warning("Error closing connection after exception in payInvoice")
        if json_response is not None: logger.debug(json_response)
        return "TIMEOUT", (feeLimit * 1000), payment_hash
    r.close()
    return resultStatus, resultFeeMSat, payment_hash

def trackPayment(paymentHash, lndServer):
    logger.info(f"Tracking payment with hash {paymentHash}")
    feeLimit = lndServer["feeLimit"]
    paymentTimeout = lndServer["paymentTimeout"]
    serverAddress = lndServer["address"]
    serverPort = lndServer["port"]
    base64paymentHash = base64.b64encode(bytes.fromhex(paymentHash))
    base64paymentHash = urllib.parse.quote(base64paymentHash)
    lndCallSuffix = f"/v2/router/track/{base64paymentHash}"
    url = f"https://{serverAddress}:{serverPort}{lndCallSuffix}"
    proxies = gettorproxies() if ".onion" in serverAddress else {}
    timeout = gettimeouts()
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    resultStatus = "UNKNOWNTRACKING"
    resultFeeMSat = 0
    headers = {"Grpc-Metadata-macaroon": lndServer["macaroon"]}
    headers["Connection"] = "close"
    r = requests.get(url=url,stream=True,timeout=timeout,proxies=proxies,headers=headers,verify=False)
    try:
        for raw_response in r.iter_lines():
            logger.debug(f"- line received from server: {raw_response}")
            json_response = json.loads(raw_response)
            if "result" in json_response: 
                logger.debug("- data nested in result, promoting inner content")
                json_response = json_response["result"]
            if "message" in json_response:
                message = json_response["message"]
                logger.info(f"- {message}")
            newStatus = resultStatus
            if "status" in json_response:
                newStatus = json_response["status"]
            else:
                logger.warning("- status not found")
                newStatus = "NOTFOUND"
            if "fee_msat" in json_response:
                resultFeeMSat = int(json_response["fee_msat"])
            else:
                logger.warning("- fee_msat not found")
            if newStatus != resultStatus:
                resultStatus = newStatus
                if resultStatus == "SUCCEEDED":
                    logger.info(f" - {resultStatus}, routing fee paid: {resultFeeMSat} msat")
                elif resultStatus == "FAILED":
                    failureReason = "unknown failure reason"
                    if "failure_reason" in json_response:
                        failureReason = json_response["failure_reason"]
                    logger.warning(f" - {resultStatus} : {failureReason}")
                elif resultStatus == "IN_FLIGHT":
                    logger.debug(f" - {resultStatus}")
                else:
                    logger.info(f" - {resultStatus}")
                    logger.info(json_response)
    except Exception as rte: # (ConnectionError, TimeoutError, ReadTimeoutError) as rte:
        try:
            r.close()
        except Exception as e:
            logger.warning("Error closing connection after exception in trackPayment")
        if json_response is not None: logger.debug(json_response)
        return "TIMEOUT", (feeLimit * 1000)
    r.close()
    return resultStatus, resultFeeMSat

def recheckTimedout(d, lndServer):
    global statusCounts
    adjustedCount = 0
    reducedFees = 0
    for k in d.keys():
        s = d[k]
        if "payment_status" not in s: continue
        ostatus = s["payment_status"]
        if ostatus not in ("TIMEOUT","UNKNOWNPAYING","UNKNOWNTRACKING","NOTFOUND"): continue
        if "payment_hash" not in s: continue
        if adjustedCount == 0: 
            logLine()
            logger.info("Rechecking lightning payments previously reported as timed out")
            logLine()
        ph = s["payment_hash"]
        f = 0
        if "fee_msat" in s: f = s["fee_msat"]
        paymentStatus, feeMSat = trackPayment(ph, lndServer)
        if paymentStatus is None: continue
        if paymentStatus == "TIMEOUT": continue
        adjustedCount += 1
        d[k]["payment_status"] = paymentStatus
        d[k]["fee_msat"] = feeMSat
        reducedFees += (f - feeMSat)
        if paymentStatus in statusCounts:
            statusCounts[paymentStatus] = statusCounts[paymentStatus] + 1
        else:
            statusCounts[paymentStatus] = 1
        if ostatus in statusCounts:
            statusCounts[ostatus] = statusCounts[ostatus] - 1
            if statusCounts[ostatus] == 0:
                del statusCounts[ostatus]

    return d, adjustedCount, reducedFees

def reviewEvents():
    global bestEventForPubkey   # w
    global statusCounts         # w
    global participantPubkeys   # w
    global zapConditions        # r
    logLine()
    logger.info("Reviewing Events")
    logLine()
    for msgEvent in foundEvents:
        logLine()
        if not isValidSignature(msgEvent.event):
            logger.warning(f"Event has invalid signature, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        publisherPubkey = msgEvent.event.public_key
        publisherEventId = msgEvent.event.id
        eventContent = msgEvent.event.content
        logger.debug(f"Reviewing event")
        logger.debug(f" - id     : {publisherEventId}")
        logger.debug(f" - pubkey : {publisherPubkey}")
        logger.debug(f" - content: {eventContent}")
        # add to participants if not yet present
        if publisherPubkey not in participantPubkeys:
            participantPubkeys.append(publisherPubkey)
        # check if pubkey on exclusion list
        if publisherPubkey in excludePubkeys:
            logger.debug(f"User {publisherPubkey} is on exclusion list, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        publisherPubkeyBech32 = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey)).bech32()
        if publisherPubkeyBech32 in excludePubkeys:
            logger.debug(f"User {publisherPubkeyBech32} is on exclusion list, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # check if content has words on exclusion list
        for ecPhrase in excludeContent:
            if ecPhrase in eventContent:
                logger.debug(f"Content {ecPhrase} is on exclusion list, skipping")
                statusCounts["SKIPPED"] += 1
                continue
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
        # We have amount to be zapped if condition was found
        if not conditionFound: 
            logger.debug(f"Content from {publisherPubkey} didnt meet zap conditions, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        else:
            logger.info(f"Conditions matched. Planning to zap {satsToZap} sats to {publisherPubkey}")
            assignIt = True
            if publisherPubkey in bestEventForPubkey:
                # update event to zap and amount if the amount is more
                assignIt = False
                currentSatsToZap = bestEventForPubkey[publisherPubkey]["amount"]
                if currentSatsToZap < satsToZap:
                    logger.debug(f"-- was previously going to zap {currentSatsToZap}")
                    assignIt = True
            if assignIt:
                bestEventForPubkey[publisherPubkey] = {
                    "eventId": publisherEventId,
                    "amount": satsToZap
                }

def zapEvents():
    global bestEventForPubkey       # r
    global cycleFeesPaid            # w
    global cycleSatsPaid            # w
    global lndServer                # r
    global paidLuds                 # w
    global paidPubkeys              # w
    global pubkey2LightningIdCache  # w
    global unzappablePubkeys        # w

    # Proceed with zaps of the events that matched
    logLine()
    logger.info("Zapping Events!")
    logLine()
    for publisherPubkey, eventToZap in bestEventForPubkey.items(): 
        logLine()
        # Get pubkey in npub form
        bech32Pubkey = PublicKey(raw_bytes=bytes.fromhex(publisherPubkey)).bech32()
        logger.debug(f"Pubkey: {bech32Pubkey}")
        # Skip any already paid (from prior runs)
        if publisherPubkey in paidPubkeys: 
            logger.debug(f"User was already paid for this event, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # Reassign the event to zap and the amount
        publisherEventId = eventToZap["eventId"]
        satsToZap = eventToZap["amount"]
        # Get lightning id for user
        if publisherPubkey in pubkey2LightningIdCache:
            lightningId = pubkey2LightningIdCache[publisherPubkey]
        else:
            lightningId = getLightningIdForPubkey(publisherPubkey)
            if lightningId is None:
                logger.info(f"Unable to zap user. No lightning address found in profile, skipping")
                if publisherPubkey not in unzappablePubkeys:
                    unzappablePubkeys.append(publisherPubkey)
                statusCounts["SKIPPED"] += 1
                continue
            identityParts = lightningId.split("@")
            if len(identityParts) != 2: 
                logger.debug(f"Lightning address for User {lightningId} is invalid, skipping")
                statusCounts["SKIPPED"] += 1
                continue
            pubkey2LightningIdCache[publisherPubkey] = lightningId
            savePubkey2LightningCache(pubkey2LightningIdCache)
        logger.debug(f"Lightning Address: {lightningId}")
        # Check if we've already paid this lightning user
        if lightningId in paidLuds: 
            logger.debug(f"Lightning address for User {lightningId} was already paid for this event, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        # Get lnurlpay info
        lnurlPayInfo, lnurl = getLNURLPayInfo(lightningId)
        if lnurl is None:
            logger.debug(f"Lightning address for User {lightningId} is invalid, skipping")
            statusCounts["SKIPPED"] += 1
            continue
        lnurlBytes = bytes(lnurl,'utf-8')
        lnurlBits = bech32.convertbits(lnurlBytes,8,5)
        bech32lnurl = bech32.bech32_encode("lnurl", lnurlBits)
        if lnurlPayInfo is None:
            logger.warning(f"Could not get LNURL info for identity: {lightningId}. skipped")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        ## these next few fields are enforcing nostr and zaps. this is an extension
        ## of lnurlp and we could still request and pay an invoice directly that
        ## doesnt involve nostr without that, but since we want to reward promotions
        ## within nostr, i'll leave these in
        if "allowsNostr" not in lnurlPayInfo:
            logger.debug(f"LN Provider of identity {lightningId} does not support nostr. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        if not lnurlPayInfo["allowsNostr"]:
            logger.debug(f"LN Provider of identity {lightningId} does not allow nostr. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        ## this one is the payment providers pubkey which we (and others) can use to
        ## validate the zap receipt that the provider will publish to nostr
        if "nostrPubkey" not in lnurlPayInfo:
            logger.debug(f"LN Provider of identity {lightningId} does not have nostrPubkey. Zap not supported")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        #nostrPubkey = lnurlPayInfo["nostrPubkey"]
        if not all(k in lnurlPayInfo for k in ("callback","minSendable","maxSendable")): 
            logger.debug(f"LN Provider of identity {lightningId} does not have proper callback, minSendable, or maxSendable info. Zap not supported")
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
            logger.debug(f"LN Provider of identity {lightningId} does not allow zaps less than {minSendable} msat. Skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        if (satsToZap * 1000) > maxSendable:
            logger.debug(f"LN Provider of identity {lightningId} does not allow zaps greater than {maxSendable} msat. Skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # prepare and sign kind9734 request
        kind9734 = makeZapRequest(satsToZap, zapMessage, publisherPubkey, publisherEventId, bech32lnurl)
        # send to provider, requesting invoice
        invoice = getInvoiceFromZapRequest(callback, satsToZap, kind9734, bech32lnurl)
        if not isValidInvoiceResponse(invoice):
            logger.debug(f"Response from LN Provider of identity {lightningId} did not provide a valid invoice. skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # Capture verification url if provided
        verifyUrl = None
        if "verify" in invoice: verifyUrl = invoice["verify"]
        # Decode it
        paymentRequest = invoice["pr"]
        decodedInvoice = getDecodedInvoice(paymentRequest, lndServer)
        # check if within ranges
        if not isValidInvoice(decodedInvoice, satsToZap):
            logger.warning(f"Invoice from LN Provider of identity {lightningId} is unacceptable. skipping")
            if publisherPubkey not in unzappablePubkeys:
                unzappablePubkeys.append(publisherPubkey)
            statusCounts["SKIPPED"] += 1
            continue
        # ok. If we got this far, we can pay it
        paymentTime = int(time.time())
        paymentTimeHuman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        paidPubkeys[publisherPubkey] = {"lightning_id":lightningId,"amount_sat":satsToZap,"payment_time":paymentTime,"payment_time_human":paymentTimeHuman}
        if verifyUrl is not None: 
            paidPubkeys[publisherPubkey]["payment_verify_url"] = verifyUrl
        paidLuds.append(lightningId)
        statusCounts["PAYMENTATTEMPTS"] += 1
        paymentStatus, paymentFees, paymentHash = payInvoice(paymentRequest, lndServer)
        paidPubkeys[publisherPubkey]["payment_status"] = paymentStatus
        paidPubkeys[publisherPubkey]["fee_msat"] = paymentFees
        if paymentHash is not None: 
            paidPubkeys[publisherPubkey]["payment_hash"] = paymentHash
        cycleFeesPaid += paymentFees
        cycleSatsPaid += satsToZap
        if paymentStatus in statusCounts:
            statusCounts[paymentStatus] = statusCounts[paymentStatus] + 1
        else:
            statusCounts[paymentStatus] = 1
        # Save our paid every round
        savePubkeys("paid", eventId, paidPubkeys)
        savePubkeys("paidluds", eventId, paidLuds)    

def logLine():
    logger.info("-" * 60)

# Logging to systemd
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Global config
config = getConfig("config.json")

dataFolder = "data/"

if __name__ == '__main__':

    if not exists(dataFolder): os.makedirs(dataFolder)

    # Read in key config info  
    eventId = getEventId(config, "referencedEventId")
    if str(eventId).startswith("nostr:"): eventId = eventId[6:]
    if "note1" or "nevent" in eventId:
        e1, e2 = bech32.bech32_decode(eventId)
        tlv_bytes = bech32.convertbits(e2, 5, 8)[:-1]
        tlv_length = tlv_bytes[1]
        tlv_value = tlv_bytes[2:tlv_length+2]
        eventId = bytes(tlv_value).hex()
    # Add logger to file based on eventid
    fileLoggingHandler = logging.FileHandler(f"{dataFolder}{eventId}.log")
    fileLoggingHandler.setFormatter(formatter)
    logger.addHandler(fileLoggingHandler)
    botKey = getPrivateKey(config, "botPrivateKey")
    relaysC = getNostrRelays(config, "relays")
    relays = []
    for nostrRelay in relaysC:
        if str(nostrRelay).startswith("wss://"):
            relays.append(nostrRelay)
        else:
            relays.append(f"wss://{nostrRelay}")
    excludePubkeys = normalizePubkeys(getExcludePubkeys(config, "excludePubkeys"))
    excludeContent = getExcludeContent(config, "excludeConentContains")
    validateConfig(config)
    zapConditions = config["zapConditions"]
    zapMessage = getZapMessage(config, "zapMessage")
    conditionCounter = len(zapConditions)
    lndServer = config["lndServer"]

    # Pubkey to Lightning cache
    pubkey2LightningIdCache = loadPubkey2LightningCache()

    # Load existing from tracking files
    participantPubkeys = loadPubkeys("participants", eventId)
    paidPubkeys = listtodict(loadPubkeys("paid", eventId))
    paidLuds = loadPubkeys("paidluds", eventId)
    unzappablePubkeys = []
    bestEventForPubkey = {}

    # Metrics tracking
    cycleSatsPaid = 0
    cycleFeesPaid = 0
    statusCounts = {"PAYMENTATTEMPTS": 0, "SKIPPED":0}

    # Get Nostr Events referencing the event
    foundEvents = getEventsOfEvent(eventId, relays)

    # Check the events that people posted as response
    reviewEvents()
    
    # And zap!
    zapEvents()

    # Save data at end
    savePubkeys("participants", eventId, participantPubkeys)

    # check for timeouts
    paidPubkeys, resolvedCount, reducedFees = recheckTimedout(paidPubkeys, lndServer)
    cycleFeesPaid -= reducedFees
    if resolvedCount > 0: savePubkeys("paid", eventId, paidPubkeys)

    # Report for Event
    logLine()
    logger.info(f"SUMMARY")
    logLine()
    logger.info(f"Responses processed: {len(foundEvents)}")
    logger.info(f"Unique pubkeys seen: {len(participantPubkeys)}")
    logger.info(f"Total Pubkeys paid so far: {len(paidPubkeys.keys())}")
    logLine()
    logger.info("For all runs of script on this event")
    totalSatsPaid = 0
    totalFeesPaid = 0
    for paidPubkey in paidPubkeys.keys():
        if "amount_sat" in paidPubkeys[paidPubkey]: 
            totalSatsPaid += paidPubkeys[paidPubkey]["amount_sat"]
        if "fee_msat" in paidPubkeys[paidPubkey]:
            totalFeesPaid += paidPubkeys[paidPubkey]["fee_msat"]
    totalFeesAsSats = int(math.ceil(float(totalFeesPaid)/float(1000)))
    logger.info(f"Sats paid: {totalSatsPaid: >7}    sats")
    logger.info(f"Fees paid: {totalFeesPaid: >10} msats")
    logger.info( "---------------------------")
    logger.info(f"Total    : {totalSatsPaid + totalFeesAsSats} sats")

    # Report status counts for cycle
    logLine()
    logger.info("For only this run of the script")
    cycleFeesAsSats = int(math.ceil(float(cycleFeesPaid)/float(1000)))
    logger.info(f"          REVIEWED = {len(foundEvents)}")
    skipped = statusCounts["SKIPPED"]
    attempts = statusCounts["PAYMENTATTEMPTS"]
    logger.info(f"           SKIPPED = {skipped}")
    logger.info(f"  PAYMENT ATTEMPTS = {attempts}")
    for k in statusCounts.keys():
        if k in ("PAYMENTATTEMPTS","SKIPPED"): continue
        logger.info(f"    {k: >10} = {statusCounts[k]}")
    logger.info("")
    logger.info(f" Sats paid: {cycleSatsPaid: >7}    sats")
    logger.info(f" Fees paid: {cycleFeesPaid: >10} msats")
    logger.info( "---------------------------")
    logger.info(f"Cycle Total: {cycleSatsPaid + cycleFeesAsSats} sats")

    # Report unzappable
    if len(unzappablePubkeys) > 0:
        logLine()
        logger.info(f"Recent unzappable npubs: {len(unzappablePubkeys)}")
        for p in unzappablePubkeys:
            npub = PublicKey(raw_bytes=bytes.fromhex(p)).bech32()
            logger.info(f"  {npub}")



