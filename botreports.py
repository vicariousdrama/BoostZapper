#!/usr/bin/env python3
import boto3
import boto3.session
import glob
import hashlib
import os
import botledger as ledger
import botutils as utils
import botfiles as files

logger = None
config = None

def getNpubsWithEvents():
    return os.listdir(files.userEventsFolder)

def getEventsForNpub(npub):
    path = f"{files.userEventsFolder}{npub}"
    return os.listdir(path)

def makeAllReports():
    npubs = getNpubsWithEvents()
    for npub in npubs:
        makeLedgerReport(npub)
        events = getEventsForNpub(npub)
        for eventId in events:
            if os.path.isdir(os.path.join(f"{files.userEventsFolder}{npub}", eventId)):
                makeEventReport(npub, eventId)
        makeIndex(npub)

def getReportFilename(npub, eventId):
    destFolder = f"{files.userReportsFolder}{npub}/"
    utils.makeFolderIfNotExists(destFolder)
    destFile = f"{destFolder}{eventId}.html"
    return destFile

def makeEventReport(npub, eventId):
    sourceFolder = f"{files.userEventsFolder}{npub}/{eventId}/"
    utils.makeFolderIfNotExists(sourceFolder)
    sourcePaidNpubsFile = f"{sourceFolder}paidnpubs.json"
    sourcePaidNpubs = files.loadJsonFile(sourcePaidNpubsFile, {})
    destFile = getReportFilename(npub, eventId)
    logger.debug(f"Making report at {destFile}")
    destData = \
        buildEventReportHeader(npub, eventId) + \
        buildEventReportLines(sourcePaidNpubs) + \
        buildEventReportFooter(npub, eventId)
    fileChanged = saveIfFileContentDifferent(destFile, destData)
    if fileChanged: 
        uploadFile(npub=npub, srcFile=destFile, destFile=f"{eventId}.html")
    return fileChanged

def saveIfFileContentDifferent(filename, data):
    different = False
    if not os.path.exists(filename): 
        different = True
    else:
        with open(filename) as f:
            fileContent = f.read()
        different = fileContent != data
    if different:
        with open(filename, "w") as f:
            f.write(data)
    return different

def isAWSEnabled():
    if "aws" not in config: return False
    if not all(k in config["aws"] for k in (
        "enabled",
        "s3Bucket",
        "aws_access_key_id",
        "aws_secret_access_key",
        "baseKey",
        "pepper")): 
        return False
    if not config["aws"]["enabled"]: return False
    return True

def getS3Folder(npub):
    if not isAWSEnabled: return npub
    baseKey = config["aws"]["baseKey"]
    pepper = config["aws"]["pepper"]
    input = npub + pepper
    hexresult = hashlib.md5(input.encode()).hexdigest()
    result = f"{baseKey}{hexresult}"
    return result

def uploadFile(npub, srcFile=None, destFile="index.html"):
    if srcFile is None:
        logger.error(f"Source file was not provided when calling uploadFile")
        return
    s3Key = getS3Folder(npub)
    s3Key = f"{s3Key}/{destFile}"
    uploadToAWS(s3Key, srcFile)

def getReportIndexURL(npub):
    if not isAWSEnabled(): return None
    s3Key = getS3Folder(npub) + "/index.html"
    s3Bucket = config["aws"]["s3Bucket"]
    url = f"https://{s3Bucket}.s3.amazonaws.com/{s3Key}"
    return url

def uploadToAWS(s3Key, filename):
    # Get AWS info
    if not isAWSEnabled(): 
        logger.debug(f"File {filename} not uploaded. AWS not enabled")
        return
    s3Bucket = config["aws"]["s3Bucket"]
    aws_access_key_id = config["aws"]["aws_access_key_id"]
    aws_secret_access_key = config["aws"]["aws_secret_access_key"]
    # URL
    url = f"https://{s3Bucket}.s3.amazonaws.com/{s3Key}"
    # Upload to bucket
    mysession = boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key)
    s3Client = mysession.client('s3')
    s3Client.upload_file(
        Filename=filename, 
        Bucket=s3Bucket,
        Key=s3Key, 
        ExtraArgs={'ContentType':"text/html", "CacheControl": "public,max-age=86400"}
        )
    logger.debug(f"Updated {url}")

def buildEventReportHeader(npub, eventId):
    output = "<html>"
    output += "<head><style>\n"
    output += "body {font-family:DejaVuSansMono,Consolas,Monospace,Lucida Console;font-size:12pt;}\n"
    output += "table {width:100%;border-collapse:collapse;}\n"
    output += "thead {background-color:#440044;color:#ffffff;font-weight:700;font-size:12pt;}\n"
    output += "tbody {background-color:#880088;color:#ffffff;font-size:10pt;}\n"
    output += "tr.d {border-bottom: 2px solid #610061;}\n"
    output += "td {font-size:8pt;}\n"
    output += "a {color:#ffffff;}\n"
    output += "</style></head>"
    output += "<body>"
    output += f"<h3>BoostZapper report for event: {eventId}</h3>"
    output += "<p>Below are the amount of zaps recorded for the event, and the routing fees charged by peer channels</p>"
    return output

def buildEventReportLines(sourcedata):
    output = "<table>"
    i = 0
    output += "<thead><tr><td width=50>#</td><td width=150>Date</td><td>Pubkey / Lightning Address</td><td width=150>Sats Rewarded</td><td width=150>Routing Fee</td></tr></thead>"
    output += "<tbody>"
    for k,v  in sourcedata.items():
        i = i + 1
        dateiso = "unknown"
        if "payment_time_human" in v: dateiso = v["payment_time_human"]
        if "payment_time_iso" in v: dateiso = v["payment_time_iso"]
        lightning = "unknown"
        if "lightning_id" in v: lightning = v["lightning_id"]
        amount = "unknown"
        if "amount_sat" in v: amount = v["amount_sat"]
        fee = "unknown"
        if "fee_msat" in v: fee = v["fee_msat"]
        line1 = f"<tr><td rowspan=\"2\">{i}</td><td rowspan=\"2\">{dateiso}</td><td colspan=\"3\">{k}</td></tr>"
        line2 = f"<tr><td>{lightning}</td><td>{amount} sat</td><td>{fee} msat</td>"
        line3 = f"<tr class=\"d\"><td colspan=5></td></tr>"
        output += line1
        output += line2
        output += line3
    output += "</tbody>"
    output += "</table>"
    return output

def buildEventReportFooter(npub, eventId):
    output = "</body></html>"
    return output

def buildIndexHeader(npub):
    output = "<html>"
    output += "<head><style>\n"
    output += "body {font-family:DejaVuSansMono,Consolas,Monospace,Lucida Console;font-size:12pt;}\n"
    output += "table {width:100%;border-collapse:collapse;}\n"
    output += "thead {background-color:#440044;color:#ffffff;font-weight:700;font-size:12pt;}\n"
    output += "tbody {background-color:#880088;color:#ffffff;font-size:10pt;}\n"
    output += "tr.d {border-bottom: 2px solid #610061;}\n"
    output += "td {font-size:8pt;}\n"
    output += "a {color:#ffffff;}\n"
    output += "a.ledger {color:#000000;}\n"
    output += "</style></head>"
    output += "<body>"
    output += f"<h3><a class=\"ledger\" href=\"ledger.html\">Click Here For Ledger</a></h3>"
    output += f"<h3>List of Events Monitored by BoostZapper for {npub}</h3>"
    return output

def buildIndexLines(sourcedata):
    output = "<table>"
    i = 0
    output += "<thead><tr><td width=50>#</td><td width=150>Date</td><td>Note Event</td></tr></thead>"
    output += "<tbody>"
    for v in sourcedata:
        if type(v) is not dict: continue
        i = i + 1
        if not all(k in v for k in ("date_iso","eventId")): continue
        date_iso = v["date_iso"]
        eventId = v["eventId"]
        output += f"<tr><td>{i}</td><td>{date_iso}</td><td><a href=\"./{eventId}.html\">{eventId}</a></td></tr>"
        output += f"<tr class=\"d\"><td colspan=5></td></tr>"
    output += "</tbody>"
    output += "</table>"
    return output

def buildIndexFooter(npub):
    output = "</body></html>"
    return output

def getIndexFilename(npub):
    destFolder = f"{files.userReportsFolder}{npub}/"
    utils.makeFolderIfNotExists(destFolder)
    destFile = f"{destFolder}index.html"
    return destFile

def makeIndex(npub):
    sourceFolder = f"{files.userEventsFolder}{npub}/"
    utils.makeFolderIfNotExists(sourceFolder)
    eventIndexFile = f"{sourceFolder}index.json"
    eventIndex = files.loadJsonFile(eventIndexFile, [])
    eventIndex.reverse()
    destFile = getIndexFilename(npub)
    logger.debug(f"Making index at {destFile}")
    destData = \
        buildIndexHeader(npub) + \
        buildIndexLines(eventIndex) + \
        buildIndexFooter(npub)
    fileChanged = saveIfFileContentDifferent(destFile, destData)
    if fileChanged: 
        uploadFile(npub=npub, srcFile=destFile)
    return fileChanged

def getLedgerReportFilename(npub):
    destFolder = f"{files.userReportsFolder}{npub}/"
    utils.makeFolderIfNotExists(destFolder)
    destFile = f"{destFolder}ledger.html"
    return destFile

def buildLedgerReportHeader(npub):
    output = ""
    output += "<html>"
    output += "<head><style>\n"
    output += "body {font-family:DejaVuSansMono,Consolas,Monospace,Lucida Console;font-size:12pt;}\n"
    output += "table {width:100%;border-collapse:collapse;}\n"
    output += "thead {background-color:#440044;color:#ffffff;font-weight:700;font-size:12pt;}\n"
    output += "tbody {background-color:#880088;color:#ffffff;font-size:10pt;}\n"
    output += "tr.d {border-bottom: 2px solid #610061;}\n"
    output += "td {font-size:8pt;}\n"
    output += "a {color:#ffffff;}\n"
    output += "</style></head>"
    output += "<body>"
    output += f"<h3>BoostZapper ledger for {npub}</h3>"
    output += "<table>"
    output += "<thead><tr>"
    output += "<td width=150>Date</td>"
    output += "<td>Description</td>"
    output += "<td width=80 align=center>Credits</td>"
    output += "<td width=90 align=center>Zap Amount</td>"
    output += "<td width=90 align=center>Routing Cost</td>"
    output += "<td width=90 align=center>Service Fee</td>"
    output += "<td width=90 align=center>Balance</td>"
    output += "</tr></thead>"
    output += "<tbody>"
    return output    

def buildLedgerReportLines(sourcedata):
    output = ""
    linedescription = ""
    linecredits = ""
    linezap = ""
    lineroutingfee = ""
    lineservicefee = ""
    for dataEntry in sourcedata:
        if type(dataEntry) is not dict: continue
        # from the entry
        linedateiso = dataEntry["created_at_iso"]
        description = dataEntry["description"]
        entrytype = dataEntry["type"]
        credits = dataEntry["credits"]
        mcredits = dataEntry["mcredits"]
        balance = dataEntry["balance"]
        # Ignore entry if carry over
        if description == "Carry over from ledger rotation": continue
        # line management
        writeLine = False
        if linedescription == "": linedescription = description
        if entrytype == "ZAPS":
            linezap = str(credits)
        if entrytype == "ROUTING FEES":
            if description.startswith("Credit for zap payment"):
                linecredits = f"{(mcredits/1000):.3f}"
                writeLine = True
            else:
                lineroutingfee = f"{(mcredits/1000):.3f}"
        if entrytype == "SERVICE FEES":
            lineservicefee = f"{(mcredits/1000):.3f}"
            writeLine = True
        if entrytype == "INITIALIZED":
            writeLine = True
        if entrytype == "CREDITS APPLIED":
            linecredits = str(credits)
            writeLine = True
        if entrytype == "REPLY MESSAGE":
            lineservicefee = f"{(mcredits/1000):.3f}"
            writeLine = True
        # Write the line if ready
        if writeLine:
            linebalance = f"{balance:.3f}"
            output += "<tr>"
            output += f"<td>{linedateiso}</td>"
            output += f"<td>{linedescription}</td>"
            output += f"<td align=right>{linecredits}</td>"
            output += f"<td align=right>{linezap}</td>"
            output += f"<td align=right>{lineroutingfee}</td>"
            output += f"<td align=right>{lineservicefee}</td>"
            output += f"<td align=right>{linebalance}</td>"
            output += "</tr>"
            # and then reset variables
            linedescription = ""
            linecredits = ""
            linezap = ""
            lineroutingfee = ""
            lineservicefee = ""
    return output

def buildLedgerReportFooter(npub):
    output = ""
    output += "</tbody>"
    output += "</table>"
    output = "</body></html>"
    return output

def makeLedgerReport(npub):
    destFile = getLedgerReportFilename(npub)
    logger.debug(f"Making ledger report at {destFile}")
    destData = buildLedgerReportHeader(npub)
    archiveFilePattern = f"{files.userLedgerFolder}archived/{npub}*"
    archiveFiles = []
    for archiveFilename in glob.glob(archiveFilePattern):
        archiveFiles.append(archiveFilename)
    archiveFiles.sort()
    for archiveFilename in archiveFiles:
        sourcedata = files.loadJsonFile(archiveFilename)
        destData += buildLedgerReportLines(sourcedata)
    sourcedata = files.loadJsonFile(ledger.getUserLedgerFilename(npub))
    destData += buildLedgerReportLines(sourcedata)
    destData += buildLedgerReportFooter(npub)
    fileChanged = saveIfFileContentDifferent(destFile, destData)
    if fileChanged: 
        uploadFile(npub=npub, srcFile=destFile, destFile=f"ledger.html")
    return fileChanged