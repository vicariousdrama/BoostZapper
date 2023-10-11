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
    files.logger = logger
    lnd.logger = logger
    nostr.logger = logger
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
    stdoutLoggingHandler = logging.StreamHandler(stream=sys.stdout)
    stdoutLoggingHandler.setFormatter(formatter)
    logger.addHandler(stdoutLoggingHandler)
    fileLoggingHandler = logging.FileHandler(f"{files.dataFolder}logs/bot.log")
    fileLoggingHandler.setFormatter(formatter)
    logger.addHandler(fileLoggingHandler)

    # Load server config
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    nostr.config = serverConfig["nostr"]
    lnd.config = serverConfig["lnd"]

    # Bot loop
    while True:
        newMessages = nostr.checkDirectMessages()
        if len(newMessages) > 0: nostr.processDirectMessages()
        lnd.checkInvoices()
        #runBoostZapper()
        time.sleep(1)