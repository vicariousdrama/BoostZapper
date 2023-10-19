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
    # Rotate if needed
    if len(ledger) > 1000: # TODO: consider date based rotation?
        rotateLedger(npub, ledger)
    # return new balance
    return balance

def rotateLedger(npub, ledger):
    # first save current contents to the archive
    archivedLedgerFolder = f"{files.userLedgerFolder}archived/"
    utils.makeFolderIfNotExists(archivedLedgerFolder)
    t, tISO = utils.getTimes()
    archivedFilename = f"{archivedLedgerFolder}{npub}.{t}.ledger.json"
    files.saveJsonFile(archivedFilename, ledger)
    # now get balance
    ledgerSummary = {
        "CREDITS APPLIED": 0,
        "ZAPS": 0,
        "ROUTING FEES": 0,
        "SERVICE FEES": 0
    }
    for ledgerEntry in ledger:
        type = ledgerEntry["type"]
        credits = ledgerEntry["credits"]
        mcredits = ledgerEntry["mcredits"]
        if type in ledgerSummary:
            value = ledgerSummary[type]
            value += credits
            value += (mcredits/1000)
            ledgerSummary[type] = value
    newLedger = []
    balance = 0
    balance = balance + ledgerSummary["CREDITS APPLIED"]
    newLedger.append({
        "created_at": t,
        "created_at_iso": tISO,
        "type": "CREDITS APPLIED",
        "credits": ledgerSummary["CREDITS APPLIED"],
        "mcredits": 0,
        "balance": balance,
        "description": "Carry over from ledger rotation",
        })
    balance = balance + ledgerSummary["ZAPS"]
    newLedger.append({
        "created_at": t,
        "created_at_iso": tISO,
        "type": "ZAPS",
        "credits": ledgerSummary["ZAPS"],
        "mcredits": 0,
        "balance": balance,
        "description": "Carry over from ledger rotation",
        })
    balance = balance + (ledgerSummary["ROUTING FEES"]/1000)
    newLedger.append({
        "created_at": t,
        "created_at_iso": tISO,
        "type": "ROUTING FEES",
        "credits": 0,
        "mcredits": ledgerSummary["ROUTING FEES"],
        "balance": balance,
        "description": "Carry over from ledger rotation",
        })
    balance = balance + (ledgerSummary["SERVICE FEES"]/1000)
    newLedger.append({
        "created_at": t,
        "created_at_iso": tISO,
        "type": "SERVICE FEES",
        "credits": 0,
        "mcredits": ledgerSummary["SERVICE FEES"],
        "balance": balance,
        "description": "Carry over from ledger rotation",
        })
    filename = getUserLedgerFilename(npub)
    files.saveJsonFile(filename, ledger)
    
    
