#!/usr/bin/env python3
from collections import OrderedDict
from datetime import datetime
import logging
import random
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
    fileLoggingHandler = logging.FileHandler(f"{files.logFolder}bot.log")
    fileLoggingHandler.setFormatter(formatter)
    logger.addHandler(fileLoggingHandler)
    files.logger = logger
    lnd.logger = logger
    lnurl.logger = logger
    nostr.logger = logger

    # Load server config
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
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

    lastEventTime = 0

    # Bot loop
    while True:
        loopStartTime = int(time.time())

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
                relays = botConfig["relays"]
                since = -1
                if "eventSince" not in botConfig:
                    event = nostr.getEvent(eventHex)
                    if event is not None: 
                        since = event.created_at
                        nostr.setNostrFieldForNpub(npub, "eventSince", since)
                else:
                    since = botConfig["eventSince"]
                if since is None or since == "" or since == -1:
                    # event not found on relay - disable it
                    logger.warning(f"Event {eventHex} for {npub} wasn't found on relays")
                    nostr.sendDirectMessage(npub, "Could not find event on relays")
                    nostr.handleEnable(npub, False)
                else:
                    # until can be up to 2 hours, but not newer then now
                    until = since + (2 * 60 * 60)
                    if until > int(time.time()): until = int(time.time())
                    responseEvents = nostr.getResponseEventsForEvent(eventHex, relays, since, until)
                    since = nostr.processEvents(responseEvents, npub, botConfig)
                    nostr.setNostrFieldForNpub(npub, "eventSince", since)
        else:
            enabledBots = nostr.getEnabledBots()

        # todo: track payments every 15 minutes?

        # sleep if we can
        loopEndTime = int(time.time())
        noLaterThan = loopStartTime + sleepTime
        if noLaterThan > loopEndTime:
            time2sleep = noLaterThan - loopEndTime
            logger.debug(f"Sleeping for {time2sleep}")
            time.sleep(time2sleep)
