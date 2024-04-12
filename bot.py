#!/usr/bin/env python3
from collections import OrderedDict
from logging.handlers import RotatingFileHandler
import logging
import random
import shutil
import sys
import threading
import time
import botfiles as files
import botledger as ledger
import botlnd as lnd
import botlnurl as lnurl
import botnostr as nostr
import botreports as reports
import botutils as utils

def processBots():
    global enabledBots
    global foundTracker
    if len(enabledBots.keys()) > 0:
        # next npub's config
        npub, eventHex = enabledBots.popitem(last=False)
        botConfig = nostr.getNpubConfigFile(npub)

        # check outstanding payments status
        d100 = random.randint(1,100)
        percentCheckOutstandingPayments = 25
        if d100 <= percentCheckOutstandingPayments:
            nostr.processOutstandingPayments(npub, botConfig)

        # get any new replies seen on relays
        responseEvents = nostr.getEventReplies(eventHex)
        newEventsCount = len(responseEvents)
        logger.debug(f"Found {newEventsCount} replies to {eventHex} via common botRelayManager")
        if (newEventsCount == 0):
            responseEvents = nostr.getEventRepliesToNpub(npub, eventHex)
            newEventsCount = len(responseEvents)
            logger.debug(f"Found {newEventsCount} replies to {eventHex} via inbox for {npub}")

        # process em!
        newsince = nostr.processEvents(npub, responseEvents, botConfig)
    
    # When all bots processed
    if len(enabledBots.keys()) == 0:
        # Repopulate the list of enabled bots
        enabledBots = nostr.getEnabledBots()

def billForTime():
    global startTime
    global unitsBilled
    currentTime, _ = utils.getTimes()
    upTime = currentTime - startTime
    unitsRan = int(upTime / 864)
    if unitsBilled < unitsRan:
        unitsToBill = unitsRan - unitsBilled
        for npub in enabledBots.keys():
            balance = ledger.getCreditBalance(npub)
            if balance > 0:
                secondsBilled = (unitsToBill * 864)
                balance = ledger.recordEntry(npub, "SERVICE FEES", 0, -1 * feeTime864 * unitsToBill, f"{unitsToBill} time unit monitoring event for past {secondsBilled} seconds")
            if balance < 0:
                nostr.handleEnable(npub, False)
                # if npub in foundTracker:
                #     del foundTracker[npub]
        unitsBilled += unitsToBill    

if __name__ == '__main__':

    startTime, _ = utils.getTimes()

    # Logging to systemd
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
    stdoutLoggingHandler = logging.StreamHandler(stream=sys.stdout)
    stdoutLoggingHandler.setFormatter(formatter)
    logging.Formatter.converter = time.gmtime
    logger.addHandler(stdoutLoggingHandler)
    logFile = f"{files.logFolder}bot.log"
    fileLoggingHandler = RotatingFileHandler(logFile, mode='a', maxBytes=10*1024*1024, 
                                 backupCount=21, encoding=None, delay=0)
    fileLoggingHandler.setFormatter(formatter)
    logger.addHandler(fileLoggingHandler)
    files.logger = logger
    lnd.logger = logger
    lnurl.logger = logger
    nostr.logger = logger
    reports.logger = logger

    # Load server config
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    if len(serverConfig.keys()) == 0:
        shutil.copy("sample-serverconfig.json", f"{files.dataFolder}serverconfig.json")
        logger.info(f"Copied sample-server.config.json to {files.dataFolder}serverconfig.json")
        logger.info("You will need to modify this file to setup Bot private key and LND connection settings")
        quit()
    nostr.config = serverConfig["nostr"]
    lnd.config = serverConfig["lnd"]
    lnurl.config = serverConfig["lnurl"]
    reports.config = serverConfig["reports"]

    # Connect to relays
    nostr.connectToRelays()

    # Load Lightning ID cache
    nostr.loadLightningIdCache()

    # Build and upload reports
    reports.makeAllReports()
    lastReportTime = startTime
    makeReportsInterval = (1 * 60 * 60)

    # Update bot profile if changed
    nostr.checkMainBotProfile()

    # Get initial enabled bots
    enabledBots = OrderedDict()
    enabledBots = nostr.getEnabledBots()

    sleepMin = 5
    sleepMax = 15
    sleepGrowth = 1.2
    sleepTime = sleepMin

    jan012020 = 1577836800
    timeChunk = 2 * 60 * 60 # 2 hours
    upTime = 0
    unitsBilled = 0
    feeTime864 = 1000
    fees = None
    if "fees" in nostr.config: fees = nostr.config["fees"]
    if fees is not None and "time864" in fees: feeTime864 = fees["time864"]

    lastRelayReconnectTime = startTime
    relayReconnectInterval = (30 * 60)
    botProcessTime = startTime
    botProcessInterval = (2 * 60)

    # Bot loop
    while True:
        loopStartTime, _ = utils.getTimes()

        # process outstanding invoices
        lnd.checkInvoices()

        # process the next enabled bot
        if botProcessTime + botProcessInterval < loopStartTime:
            processBots()
            botProcessTime, _ = utils.getTimes()

        # look for command and control messages
        newMessages = nostr.checkDirectMessages()
        if len(newMessages) > 0:
            sleepTime = sleepMin 
            nostr.processDirectMessages(newMessages)
        else:
            sleepTime = min(sleepTime * sleepGrowth, sleepMax)

        # time billing
        billForTime()

        # process part of loop end time
        loopEndTime, _ = utils.getTimes()

        # make reports periodically
        if lastReportTime + makeReportsInterval < loopEndTime:
            reports.makeAllReports()
            lastReportTime, _ = utils.getTimes()

        # reconnect relays if periodically
        if lastRelayReconnectTime + relayReconnectInterval < loopEndTime:
            nostr.reconnectRelays()
            lastRelayReconnectTime, _ = utils.getTimes()
        # otherwise, sleep if possible
        else:
            noLaterThan = loopStartTime + sleepTime
            if noLaterThan > loopEndTime:
                time2sleep = noLaterThan - loopEndTime
                if time2sleep > sleepMax: time2sleep = sleepMax
            else:
                time2sleep = 2 # force it to avoid relay throttle
            if time2sleep > 0:
                logger.debug(f"Sleeping {time2sleep} seconds")
                time.sleep(time2sleep)
