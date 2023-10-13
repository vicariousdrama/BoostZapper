#!/usr/bin/env python3
import botfiles as files
import botutils as utils

def getUserLedgerFilename(npub):
    filename = f"{files.userLedgerFolder}{npub}.ledger.json"
    return filename

def getCreditBalance(npub):
    filename = getUserLedgerFilename(npub)
    ledger = files.loadJsonFile(filename)
    if ledger is None: return 0
    balance = int(ledger[-1]["balance"])
    return balance

def recordEntry(npub, type, credits, mcredits, description):
    filename = getUserLedgerFilename(npub)
    ledger = files.loadJsonFile(filename)
    if ledger is None: 
        # initialize first entry
        ledger = []
        balance = 0.000
        created_at, created_at_iso = utils.getTimes()
        firstEntry = {
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "type": "INITIALIZED",
            "credits": 0,
            "mcredits": 0,
            "balance": balance,
            "description": "Initialized Balance",
            }
        ledger.append(firstEntry)
    else:
        # get current balance from existing, last record
        balance = ledger[-1]["balance"]
    # Determine new balance based on amounts passed in
    balance += credits
    balance += (mcredits/1000)
    # Add the new entry
    created_at, created_at_iso = utils.getTimes()
    newEntry = {
        "created_at": created_at,
        "created_at_iso": created_at_iso,
        "type": type,
        "credits": credits,
        "mcredits": mcredits,
        "balance": balance,
        "description": description,
        }
    ledger.append(newEntry)
    # Save to disk
    files.saveJsonFile(filename, ledger)
    # return new balance
    return balance