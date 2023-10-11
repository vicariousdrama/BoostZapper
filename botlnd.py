#!/usr/bin/env python3
from urllib3.exceptions import InsecureRequestWarning, ReadTimeoutError
import base64
import json
import os
import requests
import urllib
import botfiles as files
import botnostr as nostr
import botutils as utils
import botledger as ledger

# suppress warnings as verify will be set to false for self-signed nodes
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

logger = None
config = None

def getLNDUrl(suffix):
    serverAddress = config["address"]
    serverPort = config["port"]

def getLNDHeaders():
    headers = {
        "Grpc-Metadata-macaroon": config["macaroon"],
        "Connection": "close"
        }
    return headers

def getLNDTimeouts():
    connectTimeout = 5
    readTimeout = 10    # TODO: make configurable?
    return (connectTimeout, readTimeout)

def getLNDProxies():
    if str(config["address"]).endswith(".onion"):
        return {'http': 'socks5h://127.0.0.1:9050','https': 'socks5h://127.0.0.1:9050'}
    else:
        return {}

def restLndGET(suffix):
    try:
        url = getLNDUrl(suffix)
        timeout = getLNDTimeouts()
        proxies = getLNDProxies()
        headers = getLNDHeaders()
        # Call it, non streaming
        response = requests.get(url=url,timeout=timeout,proxies=proxies,headers=headers,verify=False)
        response.status_code 
        output = response.text
        return json.loads(output)
    except Exception as e:
        logger.warning(f"Error retrieving data from LND for {suffix}: {e}")
        return None

def restLndPOST(suffix, lndPostData):
    try:
        url = getLNDUrl(suffix)
        timeout = getLNDTimeouts()
        proxies = getLNDProxies()
        headers = getLNDHeaders()
        # Call it, non streaming
        response = requests.post(url=url,data=json.dumps(lndPostData),timeout=timeout,proxies=proxies,headers=headers,verify=False)
        response.status_code 
        output = response.text
        return json.loads(output)
    except Exception as e:
        logger.warning(f"Error retrieving data from LND for {suffix}: {e}")
        return None

def createInvoice(amount=21000, memo=None, expiry=86400):
    # need to set r_preimage: The hex-encoded preimage (32 byte) which 
    # will allow settling an incoming HTLC payable to this preimage. 
    # When using REST, this field must be encoded as base64.
    r_preimage_bytes = os.urandom(32)
    r_preimage_base64 = base64.b64encode(r_preimage_bytes)
    data = {
        "memo": memo,
        "r_preimage": r_preimage_base64,
        "value": amount,
        "expiry": expiry
    }
    suffix = f"/v1/invoices"
    return restLndPOST(suffix, data)

# Returns invoice
def lookupInvoice(paymentHash):
    # Setup
    base64paymentHash = base64.b64encode(bytes.fromhex(paymentHash))
    base64paymentHash = urllib.parse.quote(base64paymentHash)
    suffix = f"/v2/invoices/lookup/{base64paymentHash}"
    return restLndGET(suffix)

# Returns payment status and fee_msat paid
def trackPayment(paymentHash):
    # Setup
    base64paymentHash = base64.b64encode(bytes.fromhex(paymentHash))
    base64paymentHash = urllib.parse.quote(base64paymentHash)
    suffix = f"/v2/router/track/{base64paymentHash}?no_inflight_updates=True"
    url = getLNDUrl(suffix)
    timeout = getLNDTimeouts()
    proxies = getLNDProxies()
    headers = getLNDHeaders()
    status = None
    fee_msat = None
    response = requests.get(url=url,stream=True,timeout=timeout,proxies=proxies,headers=headers,verify=False)
    try:
        for raw_response in response.iter_lines():
            json_response = json.loads(raw_response)
            if "result" in json_response: json_response = json_response["result"]
            if "message" in json_response:
                message = json_response["message"]
                logger.info(f"message: {message}")
            if "status" not in json_response:
                return "NOTFOUND", fee_msat
            status = json_response["status"]
            if status == "FAILED":
                failureReason = "unknown failure reason"
                if "failure_reason" in json_response:
                    failureReason = json_response["failure_reason"]
                logger.warning(f"{status}:{failureReason}")
            if "fee_msat" not in json_response:
                return status, fee_msat
            fee_msat = int(json_response["fee_msat"])
            return status, fee_msat
    except Exception as rte: # (ConnectionError, TimeoutError, ReadTimeoutError) as rte:
        if json_response is not None: logger.debug(json_response)
        return "TIMEOUT", fee_msat
    finally:
        try:
            response.close()
        except Exception as e:
            logger.warning("Error closing connection in trackPayment")
    return status, fee_msat

def monitorInvoice(theInvoice):
    invoices = files.loadInvoices()
    invoices.append(theInvoice)
    files.saveInvoices(invoices)

def checkInvoices():
    # currentInvoice["npub"] = npub
    # currentInvoice["created_at"] = created_at
    # currentInvoice["created_at_iso"] = created_at_iso
    # currentInvoice["amount"] = amount
    # currentInvoice["memo"] = memo
    # currentInvoice["expiry"] = expiry
    # currentInvoice["expiry_time"] = expiry_time_int
    # currentInvoice["expiry_time_iso"] = expiry_time_iso
    # currentInvoice["r_hash"] = newInvoice["r_hash"]
    # currentInvoice["payment_request"] = payment_request
    # currentInvoice["add_index"] = newInvoice["add_index"]

    invoices = files.loadInvoices()
    openInvoices = []
    for invoice in invoices:
        payment_hash = None
        if "r_hash" in invoice: payment_hash = invoice["r_hash"]
        if "payment_hash" in invoice: payment_hash = invoice["payment_hash"]
        npub = invoice["npub"]
        status = lookupInvoice(payment_hash)
        if status is None: 
            openInvoices.append(invoice) # consider still open, temp glitch?
            logger.warning(f"invoice for {npub} has no status. payment_hash for lookup is {payment_hash}")
            continue
        if "STATE" not in status and "state" not in status:
            openInvoices.append(invoice) # could be temp error?
            logger.warning(f"invoice for {npub} does not have a STATE. payment_hash for lookup is {payment_hash}")
            logger.warning(f"response of lookupInvoice: ")
            logger.warning(json.dumps(obj=status,indent=2))
            continue
        state = 0
        if "STATE" in status: state = status["STATE"]
        if "state" in status: state = status["state"]
        if state == 0:   # OPEN
            # keep considering as outstanding
            logger.debug(f"invoice for npub {npub} still open")
            openInvoices.append(invoice)
        elif state == 1: # SETTLED
            logger.debug(f"invoice for npub {npub} reported as settled")
            handlePaidInvoice(invoice)
        elif state == 2: # CANCELED
            logger.debug(f"invoice for npub {npub} has been canceled")
            handleCanceledInvoice(invoice)
        elif state == 3: # ACCEPTED
            # keep considering as outstanding
            logger.debug(f"invoice for npub {npub} accepted, not yet settled")
            openInvoices.append(invoice)
        else:
            logger.warning(f"invoice for {npub} has unrecognized state ({state}). payment_hash for lookup is {payment_hash}")
            logger.warning(f"response of lookupInvoice: ")
            logger.warning(json.dumps(obj=status,indent=2))
    files.saveInvoices(openInvoices)

def handlePaidInvoice(invoice):
    npub = invoice["npub"]
    amount = invoice["amount"]
    # Description
    message = f"Invoice paid. {amount} credits have been applied to your account"
    # Credit account
    ledger.recordEntry(npub, "CREDITS APPLIED", amount, 0, message)
    # DM user that invoice was paid
    nostr.sendDirectMessage(npub, message)
    # Clear current invoice from nostr config for pub
    nostr.setNostrFieldForNpub(npub, "currentInvoice", {})

def handleCanceledInvoice(invoice):
    npub = invoice["npub"]
    amount = invoice["amount"]
    message = f"Invoice for {amount} was canceled"
    # Credit account
    ledger.recordEntry(npub, "INVOICE CANCELED", 0, 0, message)
    # DM user that invoice was canceled
    nostr.sendDirectMessage(npub, message)
    # Clear current invoice from nostr config for pub
    nostr.setNostrFieldForNpub(npub, "currentInvoice", {})