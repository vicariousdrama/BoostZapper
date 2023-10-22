#!/usr/bin/env python3
from collections import OrderedDict
from logging.handlers import RotatingFileHandler
import logging
import random
import shutil
import sys
import time
import botfiles as files
import botledger as ledger
import botlnd as lnd
import botlnurl as lnurl
import botnostr as nostr
import botutils as utils

def processBots():
    global enabledBots
    global foundTracker
    global unitsBilled
    if len(enabledBots.keys()) > 0:
        npub, eventHex = enabledBots.popitem(last=False)
        botConfig = nostr.getNpubConfigFile(npub)
        if random.randint(1, 100) <= 5:
            # check outstanding payments status
            nostr.processOutstandingPayments(npub, botConfig)
        since = -1
        if "eventSince" in botConfig: since = botConfig["eventSince"]
        if type(since) is not int: since = 0
        if since < jan012020:
            since = 0
            if "eventCreated" in botConfig: since = botConfig["eventCreated"]
            if type(since) is not int: since = 0
            if since == 0:
                event = nostr.getEventByHex(npub, eventHex)
                if event is not None: 
                    since = event.created_at
                    nostr.setNostrFieldForNpub(npub, "eventCreated", since)
                    nostr.setNostrFieldForNpub(npub, "eventSince", since)
                    botConfig["eventCreated"] = since
                    botConfig["eventSince"] = since
                else:
                    opnpub = nostr.getOperatorNpub()
                    message = f"Event {eventHex} for {npub} wasn't found on relays"
                    if opnpub is not None and opnpub == npub:
                        nostr.sendDirectMessage(npub, message)
                    logger.warning()
        if since > jan012020:
            until = since + timeChunk
            currentTime, _ = utils.getTimes()
            upToTip = (until > currentTime)
            until = currentTime if upToTip else until
            responseEvents = nostr.getResponseEventsForEvent(npub, eventHex, since, until)
            newEventsCount = len(responseEvents)
            npubStats = foundTracker[npub] if npub in foundTracker else {"replies":0,"checks":0}
            npubStats["replies"] = npubStats["replies"] + newEventsCount
            npubStats["checks"] = npubStats["checks"] + 1
            logger.debug(f"Found {newEventsCount} events")
            newsince = nostr.processEvents(npub, responseEvents, botConfig)
            if upToTip:
                # restart at beginning to retry historical that may have failed
                # to get LN callback info with LN Provider
                since = botConfig["eventCreated"]
                npubStats["replies"] = 0
                npubStats["checks"] = 0
                logger.debug(f"Reached current time for {eventHex}, rechecking from posting time ({since})")
            else:
                # by default, bump the time chunk (2 hours)
                since = since + timeChunk
            foundTracker[npub] = npubStats
            nostr.setNostrFieldForNpub(npub, "eventSince", since)
    
    # When all bots processed
    if len(enabledBots.keys()) == 0:
        # Repopulate the list of enabled bots
        enabledBots = nostr.getEnabledBots()
        # Billing by time for enabled bots
        upTime = loopEndTime - startTime
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
                    if npub in foundTracker:
                        del foundTracker[npub]
            unitsBilled += unitsToBill

    # reconnect relays if no responses found at tip for all bots
    if len(foundTracker.keys()) == len(enabledBots) and len(enabledBots) > 0:
        replies = 0
        checks = 0
        for npubStats in foundTracker.values():
            replies = replies + npubStats["replies"]
            checks = checks + npubStats["checks"]
        if checks > 0 and replies == 0: nostr.reconnectRelays()

if __name__ == '__main__':

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

    # Load server config
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    if len(serverConfig.keys()) == 0:
        shutil.copy("sample-serverconfig.json", f"{files.dataFolder}serverconfig.json")
        logger.info(f"Copied sample-server.config.json to {files.dataFolder}serverconfig.json")
        logger.info("You will need to modify this file to setup Bot private key and LND connection settings")
        quit()
    nostr.config = serverConfig["nostr"]
    lnd.config = serverConfig["lnd"]

    # Connect to relays
    nostr.connectToRelays()

    # Load Lightning ID cache
    nostr.loadLightningIdCache()

    # Update bot profile if changed
    nostr.checkMainBotProfile()

    # Get initial enabled bots
    enabledBots = OrderedDict()
    enabledBots = nostr.getEnabledBots()

    sleepMin = 1
    sleepMax = 10
    sleepGrowth = 1.2
    sleepTime = 1

    jan012020 = 1577836800
    startTime, _ = utils.getTimes()
    timeChunk = 2 * 60 * 60 # 2 hours
    upTime = 0
    unitsBilled = 0
    feeTime864 = 1000
    fees = None
    if "fees" in nostr.config: fees = nostr.config["fees"]
    if fees is not None and "time864" in fees: feeTime864 = fees["time864"]

    foundTracker = {}
    lastBotTime = 0

    # Bot loop
    while True:
        loopStartTime, _ = utils.getTimes()

        # look for command and control messages
        newMessages = nostr.checkDirectMessages()
        sleepTime = sleepMin if len(newMessages) > 0 else min(sleepTime * sleepGrowth, sleepMax)

        # process the messages
        nostr.processDirectMessages(newMessages)

        # process outstanding invoices
        lnd.checkInvoices()

        # process the next enabled bot (2 per minute)
        if lastBotTime < loopStartTime - 30:
            processBots()
            lastBotTime, _ = utils.getTimes()

        # sleep if we can
        loopEndTime, _ = utils.getTimes()
        noLaterThan = loopStartTime + sleepTime
        if noLaterThan > loopEndTime:
            time2sleep = noLaterThan - loopEndTime
            if time2sleep > sleepMax: time2sleep = sleepMax
            logger.debug(f"Sleeping {time2sleep} seconds")
            time.sleep(time2sleep)
