#!/usr/bin/env python3
from datetime import datetime
import base64
import json
import logging
import math
import requests
import ssl
import sys
import time
import urllib.parse
import botfiles as files
import botledger as ledger
import botlnd as lnd
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
    nostr.logger = logger

    # Load server config
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    nostr.config = serverConfig["nostr"]
    lnd.config = serverConfig["lnd"]

    # Connect to relays
    nostr.connectToRelays()

    # Update bot profile if changed
    nostr.checkBotProfile()

    sleepMin = 1
    sleepMax = 10
    sleepGrowth = 1.2
    sleepTime = 1

    lastEventTime = 0

    # Bot loop
    while True:
        loopStartTime = int(time.time())

        # look for command and control messages
        newMessages = nostr.checkDirectMessages()

        # sleep growth based on whether messages are being received
        if len(newMessages) > 0: 
            nostr.processDirectMessages(newMessages)
            sleepTime = sleepMin
        else:
            sleepTime = sleepTime * sleepGrowth
            if sleepTime > sleepMax: sleepTime = sleepMax

        # process outstanding invoices
        lnd.checkInvoices()

        # process events once a minute?
        if loopStartTime - 60 > lastEventTime:
            logger.debug("Checking bots for events")
            enabledBots = nostr.getEnabledBots()
            if len(enabledBots.keys()) > 0:
                responseEvents = nostr.getEventResponsesForBots(enabledBots)
                # kick off thread to process them
            lastEventTime = loopStartTime

        # sleep if we can
        loopEndTime = int(time.time())
        noLaterThan = loopStartTime + sleepTime
        if noLaterThan > loopEndTime:
            time2sleep = noLaterThan - loopEndTime
            logger.debug(f"Sleeping for {time2sleep}")
            time.sleep(time2sleep)
