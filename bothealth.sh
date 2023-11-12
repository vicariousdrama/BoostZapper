#!/usr/bin/env bash



# loop
while true
do
    # check if log file was last modified more than 1 minute ago
    logolder=$(find ./data/logs/bot.log -not -newermt '-1 minute' | wc -l)

    # if log is old
    if [[ $logolder -gt 0 ]]; then
        # kill any existing process for the BoostZapper

        # start the process for BoostZapper

    fi

    # sleep 5 minutes
    sleep 300
done