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

def runBoostZapper():
    pass

if __name__ == '__main__':

    # Logging to systemd
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
    stdoutLoggingHandler = logging.StreamHandler(stream=sys.stdout)
    stdoutLoggingHandler.setFormatter(formatter)
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
    nostr.checkBotProfile()

    # Get initial enabled bots
    enabledBots = OrderedDict()
    enabledBots = nostr.getEnabledBots()

    sleepMin = 1
    sleepMax = 10
    sleepGrowth = 1.2
    sleepTime = 1

    jan012020 = 1577836800
    startTime, _ = utils.getTimes()
    upTime = 0
    unitsBilled = 0
    feeTime864 = 1000
    fees = None
    if "fees" in nostr.config: fees = nostr.config["fees"]
    if fees is not None and "time864" in fees: feeTime864 = fees["time864"]

    # Bot loop
    while True:
        loopStartTime, _ = utils.getTimes()

        # look for command and control messages
        logger.debug("Checking for direct message commands")
        newMessages = nostr.checkDirectMessages()

        # sleep growth based on whether messages are being received
        if len(newMessages) > 0: 
            logger.debug("Processing direct messages")
            nostr.processDirectMessages(newMessages)
            sleepTime = sleepMin
        else:
            sleepTime = sleepTime * sleepGrowth
            if sleepTime > sleepMax: sleepTime = sleepMax

        # process outstanding invoices
        logger.debug("Checking for invoices")
        lnd.checkInvoices()

        # process the next enabled bot
        if len(enabledBots.keys()) > 0:
            npub, eventHex = enabledBots.popitem(last=False)
            botConfig = nostr.getNpubConfigFile(npub)
            if random.randint(1, 100) > 90:
                nostr.processOutstandingPayments(npub, botConfig)
            else:
                since = -1
                if "eventSince" in botConfig: since = botConfig["eventSince"]
                if type(since) is not int: since = 0
                if since < jan012020:
                    since = 0
                    if "eventCreated" in botConfig: since = botConfig["eventCreated"]
                    if type(since) is not int: since = 0
                    if since == 0:
                        logger.debug(f"Getting event information for {eventHex}")
                        event = nostr.getEventByHex(eventHex)
                        if event is not None: 
                            since = event.created_at
                            nostr.setNostrFieldForNpub(npub, "eventCreated", since)
                            nostr.setNostrFieldForNpub(npub, "eventSince", since)
                            botConfig["eventCreated"] = since
                            botConfig["eventSince"] = since
                        else:
                            logger.warning(f"Event {eventHex} for {npub} wasn't found on relays")
                if since > jan012020:
                    # until can be up to 2 hours later, but not newer then now
                    until = since + (2*60*60)
                    currentTime, _ = utils.getTimes()
                    upToTip = False
                    if until > currentTime: 
                        until = currentTime
                        upToTip = True
                    responseEvents = nostr.getResponseEventsForEvent(eventHex, since, until)
                    newsince = nostr.processEvents(responseEvents, npub, botConfig)
                    if upToTip:
                        # restart at beginning to retry historical that may have failed
                        # to get LN callback info with LN Provider
                        since = 0
                        logger.debug(f"Reached the time tip for {eventHex}, rechecking from its posting time")
                    else:
                        # if no events in the window just processed, update since
                        # - add 5 minutes if time is same and less than current time minus 15 minutes
                        if (newsince == since and since < (currentTime-900)):
                            since = since + 300
                        elif (newsince != since):
                            since = newsince - 300
                        if since < botConfig["eventCreated"]:
                            logger.warning("Logic error. Since was being set to a value earlier than eventCreated")
                            since = botConfig["eventCreated"]
                    nostr.setNostrFieldForNpub(npub, "eventSince", since)
        else:
            enabledBots = nostr.getEnabledBots()
            # billing by time for enabled bots
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
                unitsBilled += unitsToBill

        # sleep if we can
        loopEndTime, _ = utils.getTimes()
        noLaterThan = loopStartTime + sleepTime
        if noLaterThan > loopEndTime:
            time2sleep = noLaterThan - loopEndTime
            logger.debug(f"Sleeping for {time2sleep}")
            time.sleep(time2sleep)
