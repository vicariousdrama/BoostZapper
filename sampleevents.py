#!~/.pyenv/boostzapper/bin/python3
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
import json
import logging
import sys
import time
import botfiles as files
import botnostr as nostr
import botutils as utils

kind = 6969  # zap poll
kind = 31922 # date based event
kind = 31923 # time based event
kind = 31924 # calendar

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
    # Load server config (using relays to retrieve events, but not dms)
    serverConfig = files.getConfig(f"{files.dataFolder}serverconfig.json")
    nostr.config = serverConfig["nostr"]

    # Defaults
    # Limit to the past 24 hours
    until, _ = utils.getTimes()
    since = until - 86400
    limit = 10
    # Notes
    kind = 1
    # Author
    author = None
    # Look at arguments
    argField = "kind"
    argValue = ""
    tagLetter = ""
    tagValueList = []
    tags = []
    if len(sys.argv) > 1:
        for argValue in sys.argv[1:]:
            if argValue.startswith("--"):
                if len(tagValueList) > 0:
                    tags.append([tagLetter,tagValueList])
                    tagLetter = ""
                    tagValueList = []
                argField = str(argValue[2:]).lower()
            else:
                logger.debug(f"Assigning value {argValue} to {argField}")
                if argField == "kind": kind = int(argValue)
                if argField == "since": since = int(argValue)
                if argField == "until": until = int(argValue)
                if argField == "limit": limit = int(argValue)
                if argField == "author": author = argValue
                if argField == "tag": 
                    if tagLetter == "":
                        tagLetter = argValue
                    else:
                        tagValueList.append(argValue)
    if len(tagValueList) > 0: tags.append([tagLetter,tagValueList])
    authors = None if author is None else [author]

    # Connect to relays
    nostr.connectToRelays()

    # Retreive notes
    subscription_id = f"my_events"
    filter = Filter(kinds=[kind],authors=authors,limit=limit,since=since,until=until)
    for t in tags:
        filter.add_arbitrary_tag(t[0], t[1])
    filters_events = Filters([filter])
    nostr.botRelayManager.add_subscription(id=subscription_id, filters=filters_events)
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters_events.to_json_array())
    message = json.dumps(request)
    logger.debug(message)
    logger.debug("---")
    nostr.botRelayManager.publish_message(message)
    time.sleep(nostr._relayPublishTime)
    nostr.siftMessagePool()
    nostr.removeSubscription(nostr.botRelayManager, subscription_id)    

    # show them
    for event in nostr._monitoredEvents:
        logger.debug(f"{event.to_message()}")
        pass

    # Disconnect from relays
    nostr.disconnectRelays()
