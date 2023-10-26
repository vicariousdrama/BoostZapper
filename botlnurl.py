#!/usr/bin/env python3
import json
import requests
import urllib.parse

logger = None
config = None

def gettimeouts():
    connectTimeout = 5
    readTimeout = 30
    if "connectTimeout" in config: connectTimeout = config["connectTimeout"]
    if "readTimeout" in config: readTimeout = config["readTimeout"]
    return (connectTimeout, readTimeout)

def gettorproxies():
    # with tor service installed, default port is 9050
    # to find the port to use, can run the following
    #     cat /etc/tor/torrc | grep SOCKSPort | grep -v "#" | awk '{print $2}'
    return {'http': 'socks5h://127.0.0.1:9050','https': 'socks5h://127.0.0.1:9050'}

def geturl(useTor=True, url=None, defaultResponse="{}", headers={}):
    try:
        proxies = gettorproxies() if useTor else {}
        timeout = gettimeouts()
        resp = requests.get(url,timeout=timeout,allow_redirects=True,proxies=proxies,headers=headers,verify=True)
        cmdoutput = resp.text
        return json.loads(cmdoutput)
    except Exception as e:
        logger.warning(f"Error getting data from LN URL Provider from url ({url}): {str(e)}")
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

def isLNURLProviderAllowed(identity):
    identityParts = identity.split("@")
    if len(identityParts) != 2: return False
    domainname = identityParts[1]
    if "denyProviders" in config:
        if domainname in config["denyProviders"]:
            return False
    return True

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
    j = geturl(useTor, url)
    return j

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

def isValidInvoiceResponse(invoiceResponse):
    if "status" in invoiceResponse:
        if invoiceResponse["status"] == "ERROR":
            errReason = "unreported reason"
            if "reason" in invoiceResponse: errReason = invoiceResponse["reason"]
            logger.warning(f"Invoice request error: {errReason}")
            return False
    if "pr" not in invoiceResponse: return False
    return True