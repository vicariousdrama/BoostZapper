#!/usr/bin/env python3
import bech32
import datetime
import os
import sys
import time

def bech32ToHex(bech32Input):
    hrp, e2 = bech32.bech32_decode(bech32Input)
    if hrp is None: return ""
    tlv_bytes = bech32.convertbits(e2, 5, 8)[:-1]
    tlv_length = tlv_bytes[1]
    tlv_value = tlv_bytes[2:tlv_length+2]
    hexOutput = bytes(tlv_value).hex()
    return hexOutput

def hexToBech32(hexInput, hrp):
    b = bytes.fromhex(hexInput)
    bits = bech32.convertbits(b,8,5)
    bech32output = bech32.bech32_encode(hrp, bits)
    return bech32output

def isHex(s):
    return set(s).issubset(set('abcdefABCDEF0123456789'))

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

def getTimes(aDate=None):
    theDate = aDate
    if aDate is None: theDate = datetime.utcnow()
    theDate.microsecond = 0
    theDate.tzinfo = None
    isoTime = theDate.isoformat(timespec="seconds")
    secTime = int(time.time())
    return secTime, isoTime    

def makeFolderIfNotExists(path):
    if not os.path.exists(path): os.makedirs(path)
