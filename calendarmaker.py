#!~/.pyenv/boostzapper/bin/python3
from nostr.event import Event
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType
import json
import logging
import sys
import time
import botfiles as files
import botnostr as nostr
import botutils as utils

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

    # Load calendar config
    calendarConfig = files.loadJsonFile(f"{files.dataFolder}calendarconfig.json")
    if calendarConfig is None:
        logger.error("Config file for calendar is empty or not json")
        quit()

    # Connect to relays
    nostr.connectToRelays()

    botPrivateKey = nostr.getBotPrivateKey()

    sleepTime = calendarConfig["frequency"]
    keepRunning = True

    # Loop
    while keepRunning:

        calendarAList = []
        currentTime, _ = utils.getTimes()

        # do each in search list
        for searchitem in calendarConfig["searchlist"]:
            kind = searchitem["kind"]
            author = searchitem["author"]

            # Setup and publish subscription
            subscription_events = "my_events"
            filters = Filters([Filter(kinds=[kind],authors=[author])])
            request = [ClientMessageType.REQUEST, subscription_events]
            request.extend(filters.to_json_array())
            message = json.dumps(request)
            nostr.botRelayManager.add_subscription(subscription_events, filters)
            nostr.botRelayManager.publish_message(message)
            time.sleep(nostr._relayPublishTime)
            # Check if needed to authenticate and publish again if need be
            if nostr.authenticateRelays(nostr.botRelayManager, botPrivateKey):
                nostr.botRelayManager.publish_message(message)
                time.sleep(nostr._relayPublishTime)
            # Sift through messages
            nostr.siftMessagePool()
            # Remove subscription
            nostr.removeSubscription(nostr.botRelayManager, subscription_events)

            # Check matching events
            _monitoredEventsTmp = []
            for event in nostr._monitoredEvents:
                # handle calendars
                if event.kind == 31924:
                    useThisCalendar = False
                    if event.tags is not None:
                        for tagset in event.tags:
                            if len(tagset) < 2: continue
                            if tagset[0] != "d": continue
                            if tagset[1] == searchitem["d"]:
                                useThisCalendar = True
                    if not useThisCalendar:
                        _monitoredEventsTmp.append(event)
                        continue
                    for tagset in event.tags:
                        if len(tagset) < 2: continue
                        if tagset[0] != "a": continue
                        calendarAList.append(tagset[1])
                # handle date and time events
                if event.kind in (31922, 31923):
                    useThisEvent = False
                    eventuuid = None
                    phrase = searchitem["phrase"]
                    if str(phrase).lower() in str(event.content).lower():
                        useThisEvent = True
                    if event.tags is not None:
                        for tagset in event.tags:
                            if len(tagset) < 2: continue
                            if tagset[0] in ("name", "description"):
                                if str(phrase).lower() in str(tagset[1]).lower():
                                    useThisEvent = True
                            if tagset[0] == "d": 
                                eventuuid = tagset[1]
                    if eventuuid is None:
                        useThisEvent = False
                    if not useThisEvent:
                        _monitoredEventsTmp.append(event)
                        continue
                    # ensure not in the past
                    startOrEndInFuture = False
                    for tagset in event.tags:
                        if len(tagset) < 2: continue
                        if tagset[0] in ("start", "end"):
                            if currentTime < int(tagset[1]): startOrEndInFuture = True
                    if not startOrEndInFuture:
                        _monitoredEventsTmp.append(event)
                        continue
                    # build up the a tag
                    avalue = f"{kind}:{event.public_key}:{eventuuid}"
                    calendarAList.append(avalue)
            nostr._monitoredEvents = _monitoredEventsTmp
                                        
        # Done checking configured calendar items and pubkeys
        kind = 31924
        content = calendarConfig["content"]
        tags = []
        tags.append(["d", calendarConfig["uuid"]])
        tags.append(["name", calendarConfig["name"]])
        tags.append(["description", calendarConfig["description"]])
        tags.append(["image", calendarConfig["image"]])
        tags.append(["p", botPrivateKey.public_key.hex(), "", "Maintainer"])
        for avalue in calendarAList:
            tags.append(["a", avalue])
        # create event and sign it
        e = Event(content=content,kind=kind,tags=tags)
        botPrivateKey.sign_event(e)

        # Send the event
        nostr.botRelayManager.publish_event(e)

        # Sleep
        if sleepTime <= 0:
            keepRunning = False
        else:
            logger.debug(f"sleeping for {sleepTime}")
            time.sleep(sleepTime)
    
    # Disconnect from relays
    nostr.disconnectRelays()
