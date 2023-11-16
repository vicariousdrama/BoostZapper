#!~/.pyenv/boostzapper/bin/python3
from nostr.event import Event
import logging
import os
import sys
import time
import botfiles as files
import botnostr as nostr

if __name__ == '__main__':

    # Logging to systemd
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s %(name)s.%(levelname)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
    stdoutLoggingHandler = logging.StreamHandler(stream=sys.stdout)
    stdoutLoggingHandler.setFormatter(formatter)
    logging.Formatter.converter = time.gmtime
    logger.addHandler(stdoutLoggingHandler)
    files.logger = logger
    nostr.logger = logger
    # Load server config (using relays, and bot identity)
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    nostr.config = serverConfig["nostr"]

    # Load up file
    if len(sys.argv) <= 1:
        logger.error("No file provided")
        quit()
    filetosign = sys.argv[1]
    if not os.path.exists(filetosign):
        logger.error("File does not exist")
        quit()
    jsonobj = files.loadJsonFile(filetosign, None)
    if jsonobj is None:
        logger.error("File was empty or not json")
        quit()

    # Prepare event
    if "content" in jsonobj:
        content = jsonobj["content"]
    else:
        content = ""
    if "kind" in jsonobj:
        kind = jsonobj["kind"]
    else:
        logger.error("kind field not found in json")
        quit()
    if "tags" in jsonobj:
        tags = jsonobj["tags"]
    else:
        tags = None
    e = Event(content=content,kind=kind,tags=tags)
    nostr.getBotPrivateKey().sign_event(e)

    # Connect to relays
    nostr.connectToRelays()

    # Send the event
    nostr.botRelayManager.publish_event(e)
    time.sleep(1)

    # Disconnect from relays
    nostr.disconnectRelays()
