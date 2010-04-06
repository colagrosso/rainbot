from datetime import datetime, timedelta
from twisted.words.xish import domish
from twisted.internet import reactor
from wokkel.xmppim import MessageProtocol, AvailablePresence

import shelve
SHELVE_NAME = "rainbot-shelve"

import u3

# strftime format
TIME_FORMAT = "%a, %m/%d/%Y %l:%M %p"

# Set all the EIO and CIO to output high.
# Remember setting these lines high turns the relays off.
ALL_OFF_COMMAND = [u3.PortDirWrite(Direction = [0, 0xff, 0xff], WriteMask = [0, 0xff, 0xff]),
                   u3.PortStateWrite(State =   [0, 0xff, 0xff], WriteMask = [0, 0xff, 0xff]) ]

# The keys are the sprinkler zones, the IO nums are the 
# LabJackPython numbers for the U3.
# My RB12 is upside-down, so CIO3 is at the top and 
# EIO0 is at the bottom.
ZONE_TO_IONUM =  { 1  : 19,     # CIO3
                   2  : 18,
                   3  : 17,
                   4  : 16,
                   5  : 15,
                   6  : 14,
                   7  : 13,
                   8  : 12,
                   9  : 11,
                   10 : 10,
                   11 : 9,
                   12 : 8  }    # EIO0

# We're going to change these all over the place anyway.
DEFAULT_RUN_TIMES_MINUTES = { 1  : 7,
                              2  : 7,
                              3  : 7,
                              4  : 7,
                              5  : 7,
                              6  : 7,
                              7  : 7,
                              8  : 7,
                              9  : 7,
                              10 : 7,
                              11 : 7,
                              12 : 7 }

# I have 12 zones. I know.
ZONE_STRING_LIST = [ str(i) for i in range(1, 13) ]

# You could configure these to your heart's content on the 
# old controller. I'm fine with these.
START_HOUR = 4
INCREMENT_DAY = 2

# How long to wait between zones
ZONE_DELAY_SECONDS = 5

class RainBotProtocol(MessageProtocol):
    def connectionMade(self):
        print "Connected!"
        self.d.getFeedback(ALL_OFF_COMMAND)
        self.scheduler = Scheduler(self, self.d)

    def connectionLost(self, reason):
        print "Disconnected!"
        self.d.getFeedback(ALL_OFF_COMMAND)
        self.scheduler.shelveConfig.close()

    def setStatus(self, statusText, show = None):
        """
        Send a presence with statusText. show is one of the allowed strings, like 'xa'.
        """
        self.send(AvailablePresence(statuses = {None: statusText}, show = show))

    def sendText(self, responseText):
        """
        Sends responseText in a message to whoever sent RainBot a message last.
        """
        reply = self._blankMessage()
        reply.addElement("body", content=responseText)        
        self.send(reply)

    def onMessage(self, msg):
        #print "Got a message", msg.toXml()
        self.lastFrom = msg["from"] # Save this to send a reply.

        if msg["type"] == 'chat' and hasattr(msg, "body") and msg.body != None:
            msgTokens = str(msg.body).split()
            msgCommand = msgTokens[0].lower()
            if len(msgCommand) > 0:
                if msgCommand == "on":
                    self.handleOn(msgTokens)
                elif msgCommand == "off":
                    self.handleOff(msgTokens)
                elif msgCommand == "pause" or msgCommand == "p":
                    self.handlePause(msgTokens)
                elif msgCommand == "run" or msgCommand == "r":
                    self.handleRun(msgTokens)
                elif msgCommand == "stop" or msgCommand == "s":
                    self.handleStop(msgTokens)
                elif msgCommand == "times" or msgCommand == "t":
                    self.handleTimes(msgTokens)
                elif msgCommand == "quit" or msgCommand == "q":
                    self.handleQuit(msgTokens)
                elif msgCommand == "last" or msgCommand == "l":
                    self.handleLast(msgTokens)
                elif msgCommand == "will" or msgCommand == "w":
                    self.handleWill(msgTokens)                    
                elif msgCommand == "help" or msgCommand == "h" or msgCommand == "?":
                    self.handleHelp(msgTokens)
                elif msgCommand in ZONE_STRING_LIST:
                    self.handleZone(msgTokens)
                else:
                    self.handleUnknownCommand(msgTokens)
            

    def handleOn(self, msgTokens):
        """
        After running the scheduler's turn on, also send the status 
        string, because it can be quite long.
        """
        responseText = "Turning on"
        self.sendText(responseText)
        statusString = self.scheduler.turnOn()
        responseText = "Turned on"
        self.sendText(responseText)
        self.sendText(statusString)

    def handleOff(self, msgTokens):
        """
        Shut it down.
        """        
        responseText = "Turning off"
        self.sendText(responseText)
        self.scheduler.turnOff()
        responseText = "Turned off"
        self.sendText(responseText)

    def handlePause(self, msgTokens):
        """
        No arguments pauses for one day. The argument can be negative (and zero), but
        it can't cause the next time to go in the past, so -1 is probably the
        only negative number you can use.
        
        If you call this function again, it will throw out the old pause and
        calculate a new pause based on when it would have run.
        """
        pauseDays = 1
        if len(msgTokens) > 1:
            try:
                pauseDays = int(msgTokens[1])
            except:
                pauseDays = 0
        if pauseDays == 1:
            responseText = "Pausing one day"
        else:
            responseText = "Pausing " + str(pauseDays) + " days"    
        self.sendText(responseText)
        statusString = self.scheduler.pauseDays(pauseDays)
        self.sendText(statusString)

    def handleRun(self, msgTokens):
        """
        Go time. It's going to get wet.
        """
        responseText = "Running"
        self.sendText(responseText)
        self.scheduler.runProgram()

    def handleStop(self, msgTokens):
        """
        Ack, I'm all wet. Stop.
        """
        responseText = "Stopping"
        self.sendText(responseText)
        self.d.getFeedback(ALL_OFF_COMMAND)
        responseText = "Stopped"
        self.sendText(responseText)
        self.setStatus(responseText)

    def handleTimes(self, msgTokens):
        """
        This is a lot of work for one function, but there are a lot of ways to
        set the time.

        times 7      # All zones to 7 minutes
        times 12 4   # Zone 12 to 4 minutes
        times *2     # Double all watering times
        times *0.5   # Halve all watering times
        times +2     # Pad times by 2 minutes
        times +-3    # Down by 3 minutes (I know)
        """
        runTimeDict = self.scheduler.shelveConfig["runTimesMinutes"]
        if len(msgTokens) == 2:
            try:
                if msgTokens[-1].startswith('*'):
                    timeScale = float(msgTokens[-1][1:])
                    for zone in (int(s) for s in ZONE_STRING_LIST):
                        runTimeDict[zone] = int(timeScale * runTimeDict[zone])
                elif msgTokens[-1].startswith('+'):
                    timePad = int(msgTokens[-1][1:])
                    for zone in (int(s) for s in ZONE_STRING_LIST):
                        runTimeDict[zone] += timePad
                else:
                    newTime = int(msgTokens[-1])
                    for zone in (int(s) for s in ZONE_STRING_LIST):
                        runTimeDict[zone] = newTime
            except Exception, e:
                self.sendText("Couldn't set run time. " + str(e))
            else:
                self.scheduler.shelveConfig["runTimesMinutes"] = runTimeDict
                self.scheduler.shelveConfig.sync()
        elif len(msgTokens) == 3:
            try:
                newTime = int(msgTokens[-1])
                thisZone = int(msgTokens[-2])
                runTimeDict[thisZone] = newTime
            except Exception, e:
                self.sendText("Couldn't set run time. " + str(e))
            else:
                self.scheduler.shelveConfig["runTimesMinutes"] = runTimeDict
                self.scheduler.shelveConfig.sync()
        responseText = "Run times"
        self.sendText(responseText)
        responseText = str(self.scheduler.shelveConfig["runTimesMinutes"])
        self.sendText(responseText)

    def handleQuit(self, msgTokens):
        """
        Exit. Hopefully you've got monit or something to start you back up.
        """
        responseText = "Quitting"
        self.sendText(responseText)
        reactor.callLater(1, reactor.stop)

    def handleLast(self, msgTokens):
        """
        This is in the status, but I want to have it sent to me anyway.
        """
        responseText = self.scheduler.lastRunStatusString
        self.sendText(responseText)

    def handleWill(self, msgTokens):
        """
        This is at the end of the status, where sometimes I can't read it.
        """
        responseText = self.scheduler.willRunStatusString
        self.sendText(responseText)

    def handleHelp(self, msgTokens):
        responseText = "Commands:\n"
        responseText += "on\n"
        responseText += "off\n"
        responseText += "pause (p) <days (default 1)>\n"
        responseText += "run (r)\n"
        responseText += "stop (s)\n"
        responseText += "times (t)\n"
        responseText += "times (t) <new time for all zones>\n"
        responseText += "times (t) *<scale for all zones>\n"
        responseText += "times (t) +<pad for all zones>\n"
        responseText += "times (t) <zone> <new time>\n"
        responseText += "last (l)\n"
        responseText += "will (w)\n"
        responseText += "quit (q)\n"
        responseText += "1..12 <time to run>\n"
        responseText += "\n"
        self.sendText(responseText)

    def handleZone(self, msgTokens):
        """
        You can pass a custom run time, as in
        
        12     # Run zone 12 for its set time
        12 1   # Run zone 12 for 1 minute
        """
        zoneStr = msgTokens[0]
        customRunTime = None
        if len(msgTokens) > 1:
            try:
                customRunTime = int(msgTokens[1])
            except:
                pass
        if zoneStr in ZONE_STRING_LIST:
            responseText = "Zone " + zoneStr
            self.sendText(responseText)
            zone = int(zoneStr)
            runTime = self.scheduler.runZone(zone, singleZone = True, customRunTime = customRunTime)
            responseText = "Running for : " + str(runTime)
            if runTime == 1:
                responseText += " minute."
            else:
                responseText += " minutes."
            self.sendText(responseText)
        else:
            responseText = "Unknown zone: " + zoneStr
            self.sendText(responseText)

    def handleUnknownCommand(self, msgTokens):
        responseText = "Unknown command: " + msgTokens[0]
        self.sendText(responseText)

    def _blankMessage(self):            
        """
        Just add body, as in
            reply = self._blankMessage()
            reply.addElement("body", content=responseText)
        """
        reply = domish.Element((None, "message"))
        reply["to"] = self.lastFrom
        reply["from"] = self.parent.jid.full()
        reply["type"] = 'chat'
        return reply

class SchedulerState(object):
    """
    Yay, state machines.
    """
    SCHEDULER_OFF, SCHEDULER_ON, SCHEDULER_RUNNING_SCHEDULED, SCHEDULER_RUNNING_MANUAL = range(4)

class Scheduler(object):

    def __init__(self, im, d):
        self.im = im
        self.d = d
        self.nextScheduledRun = None
        self.lastRunStatusString = ""
        self.willRunStatusString = ""
        self.shelveConfig = shelve.open(SHELVE_NAME)


        # Check the shelve dictionary for
        #     lastRun : Last run time
        #     onState : Whether the sprinklers start on
        #     runTimesMinutes : Dictionary of how long to run each zone
        # I call .sync() on it after assigning to it because I'm just that way
        try:
            self.lastRunStatusString = "Last run: " + self.shelveConfig["lastRun"].strftime(TIME_FORMAT) + ". "
        except:
            self.lastRunStatusString = "Last run: unknown. "
            self.shelveConfig["lastRun"] = datetime.now()
        try:
            self.shelveConfig["onState"]
        except:
            self.shelveConfig["onState"] = True
            self.shelveConfig.sync()
        try:
            self.shelveConfig["runTimesMinutes"].keys()
        except:
            self.shelveConfig["runTimesMinutes"] = DEFAULT_RUN_TIMES_MINUTES
            self.shelveConfig.sync()

        if self.shelveConfig["onState"]:
            self.scheduleNextRun()
        else:
            self.turnOff()

    def scheduleNextRun(self, pauseDelay = None):
        """
        The optional pauseDelay is a timedelta of extra time to add on the 
        time to run next.
        """
        # We are definitely on
        self.shelveConfig["onState"] = True
        self.shelveConfig.sync()
        self.state = SchedulerState.SCHEDULER_ON

        # Cancel any previously scheduled runs
        if self.nextScheduledRun:
            if self.nextScheduledRun.active():
                self.nextScheduledRun.cancel()
            self.nextScheduledRun = None
        
        # Calculate number of seconds till it's time to run
        now = datetime.now()
        lastRunTime = self.shelveConfig["lastRun"]
        timeToRun = lastRunTime.replace(hour = START_HOUR, minute = 0, second = 0) # Love that .replace() from datetime
        while lastRunTime > timeToRun or now > timeToRun:
            timeToRun += timedelta(days = INCREMENT_DAY)
        if pauseDelay:
            timeToRun += pauseDelay
        timeTillRun = timeToRun - now
        timeTillRunSeconds = _td_to_seconds(timeTillRun)

        self.nextScheduledRun = reactor.callLater(timeTillRunSeconds, self.runProgram)
        self.willRunStatusString = "Will run: " + timeToRun.strftime(TIME_FORMAT) + "."
        try:
            self.im.setStatus(self.lastRunStatusString + self.willRunStatusString)
        except:
            pass
        return self.lastRunStatusString + self.willRunStatusString

    def turnOn(self):
        return self.scheduleNextRun()

    def turnOff(self):
        """
        Set the off state, turn off all zones, and set the red light.
        """
        self.shelveConfig["onState"] = False
        self.shelveConfig.sync()
        self.state = SchedulerState.SCHEDULER_OFF
        self.willRunStatusString = "Sprinklers off"
        self.turnOffAllZones()
        if self.nextScheduledRun:
            if self.nextScheduledRun.active():
                self.nextScheduledRun.cancel()
            self.nextScheduledRun = None
        self.im.setStatus("Sprinklers off", show = "xa") # Red light in the status

    def pauseDays(self, numDays):
        """
        Reschedule the next run with an extra pause of numDays.
        
        Doesn't do anything if the sprinklers are off.
        """
        if self.state != SchedulerState.SCHEDULER_OFF:
            return self.scheduleNextRun(timedelta(days = numDays))
        else:
            return "Not pausing because sprinklers are off."

    def runProgram(self, manual = False):
        """
        Run all the zones.
        
        If run in manual mode, don't mess with the next scheduled run.
        
        If run in regularly scheduled mode, schedule the next run when
        all the zones are done.
        """
        if manual:
            self.state = SchedulerState.SCHEDULER_RUNNING_MANUAL
        else:
            self.state = SchedulerState.SCHEDULER_RUNNING_SCHEDULED
        self.im.setStatus("Running program")
        self.runZone(1, singleZone = False)

    def runZone(self, zone, singleZone = False, customRunTime = None):
        """
        Run one zone, zone.
        
        If running as singleZone, end of story. If not, schedule the next
        zone after this.
        
        Pass in customRunTime (minutes) or use the configured time.

        Returns the number of minutes it will run for so it can be
        sent as a response message.
        """
        self.im.setStatus("Running zone: " + str(zone))
        try:
            thisRunTimeSeconds = 60 * self.shelveConfig["runTimesMinutes"][zone]
            if customRunTime:
                thisRunTimeSeconds = 60 * customRunTime
            reactor.callLater(0, self.turnOnZone, zone)
            if singleZone:
                reactor.callLater(thisRunTimeSeconds, self.ranLastZone)
            else:
                reactor.callLater(thisRunTimeSeconds, self.runNextZone, zone)
            return thisRunTimeSeconds // 60
        except Exception, e:
            self.im.setStatus("Couldn't run zone: " + str(zone) + ". Exception: " + str(e))

    def runNextZone(self, zone):
        """
        Breathe for a moment, then run the next zone.
        """
        self.im.setStatus("Finished zone: " + str(zone))
        if zone < len(ZONE_STRING_LIST):
            nextZone = zone + 1
            reactor.callLater(ZONE_DELAY_SECONDS, self.runZone, nextZone, singleZone = False)
        else:
            reactor.callLater(ZONE_DELAY_SECONDS, self.ranLastZone)
    
    def ranLastZone(self):
        """
        Another successful watering. I can see the grass greener already.
        
        Shut everything down, make some notes, and schedule another run if needed.
        """
        self.turnOffAllZones()
        if self.state == SchedulerState.SCHEDULER_RUNNING_SCHEDULED:
            self.scheduleNextRun()
        self.state = SchedulerState.SCHEDULER_ON
        lastRunTime = self.shelveConfig["lastRun"] = datetime.now()
        self.shelveConfig.sync()
        self.lastRunStatusString = "Last run: " + lastRunTime.strftime(TIME_FORMAT) + ". "
        self.im.setStatus(self.lastRunStatusString + self.willRunStatusString)

    def turnOnZone(self, zone):
        """
        Use the LabJackPython BitStateWrite to change a single EIO or CI0.
        
        Remember setting the line low turns the relay on.
        """
        self.d.getFeedback(ALL_OFF_COMMAND)
        self.d.getFeedback(u3.BitStateWrite(ZONE_TO_IONUM[zone], 0))

    def turnOffAllZones(self):
        """
        An all-around handy thing to do.
        """
        self.d.getFeedback(ALL_OFF_COMMAND)

def _td_to_seconds(td):
    '''Convert a timedelta to seconds'''
    return td.seconds + td.days * 24 * 60 * 60
