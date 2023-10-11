#!/usr/bin/env python3
from os import exists
import json
import botutils as utils

logger = None       # set by calling setLogger

# Make common folders if not already present
dataFolder = "data/"
userConfigFolder = f"{dataFolder}users"
utils.makeFolderIfNotExists(dataFolder)
utils.makeFolderIfNotExists(userConfigFolder)

def loadJsonFile(filename):
    if not exists(filename): return None
    with open(filename) as f:
        return(json.load(f))

def saveJsonFile(filename, obj):
    with open(filename, "w") as f:
        f.write(json.dumps(obj=obj,indent=2))

def getConfig(filename):
    c = utils.getCommandArg("config") # allow overriding default filename
    if c is not None: filename = c
    logger.debug(f"Loading config from {filename}")
    if not exists(filename):
        logger.warning(f"Config file does not exist at {filename}")
        return {}
    return loadJsonFile(filename)    

def loadInvoices():
    filename = f"{dataFolder}outstandingInvoices.json"
    if not exists(filename): return []
    return loadJsonFile(filename)

def saveInvoices(outstandingInvoices):
    filename = f"{dataFolder}outstandingInvoices.json"
    saveJsonFile(filename, outstandingInvoices)


