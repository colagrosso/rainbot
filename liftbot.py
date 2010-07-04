from twisted.words.xish import domish
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from wokkel.xmppim import MessageProtocol, AvailablePresence

from rainbot import RainBotProtocol
import u3

BIG_DOOR_BUTTON    = u3.FIO4
BIG_DOOR_SENSOR    = u3.FIO7
LITTLE_DOOR_BUTTON = u3.FIO5
LITTLE_DOOR_SENSOR = u3.FIO6

SAMPLE_PERIOD = 1

PUSH_TIME = 3 # Seconds to hold the button down for

# Set buttons for digital output low and sensors for digital input
# Also set DAC0 to 0 V
INIT_IO_COMMAND = [u3.BitDirWrite(BIG_DOOR_SENSOR, 0),
                   u3.BitDirWrite(LITTLE_DOOR_SENSOR, 0),
                   u3.DAC0_16(0)
                  ]

# Set buttons for analog input (Hi-Z) plus the INIT_IO_COMMAND
def initU3(d):
    d.configAnalog(BIG_DOOR_BUTTON, LITTLE_DOOR_BUTTON)
    d.getFeedback(INIT_IO_COMMAND)

def powerOnOpener(d):
    """Provide power to the opener."""
    commandList = [u3.DAC0_16(int(3.3 / 5 * 65535))]
    d.getFeedback(commandList)

def powerOffOpener(d):
    """Cut power to the opener."""
    commandList = [u3.DAC0_16(0)]
    d.getFeedback(commandList)

def pressBigDoorButton(d):
    """Set BIG_DOOR_BUTTON digital output high."""
    d.configDigital(BIG_DOOR_BUTTON)
    commandList = [u3.BitDirWrite(BIG_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(BIG_DOOR_BUTTON, 1)]
    d.getFeedback(commandList)
    
def releaseBigDoorButton(d):
    """Set BIG_DOOR_BUTTON analog input."""
    d.configAnalog(BIG_DOOR_BUTTON)

def pressLittleDoorButton(d):
    """Set LITTLE_DOOR_BUTTON digital output high."""
    d.configDigital(LITTLE_DOOR_BUTTON)
    commandList = [u3.BitDirWrite(LITTLE_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(LITTLE_DOOR_BUTTON, 1)]
    d.getFeedback(commandList)

def releaseLittleDoorButton(d):
    """Set LITTLE_DOOR_BUTTON analog input."""
    d.configAnalog(LITTLE_DOOR_BUTTON)

class DoorState(object):
    """Track which doors are open"""
    def __init__(self, bigDoorUp, littleDoorUp):
        self.bigDoorUp = bigDoorUp
        self.littleDoorUp = littleDoorUp

    def __str__(self):
        if self.bigDoorUp:
            if self.littleDoorUp:
                return "Both doors open"
            else:
                return "Big door open"
        else:
            if self.littleDoorUp:
                return "Little door open"
            else:
                return "Doors closed"
    
    def __eq__(self, b):
        return self.bigDoorUp == b.bigDoorUp and self.littleDoorUp == b.littleDoorUp

def getDoorState(d):
    """Read the state of BIG_DOOR_SENSOR and LITTLE_DOOR_SENSOR
    """
    commandList = [u3.BitStateRead(BIG_DOOR_SENSOR), 
                   u3.BitStateRead(LITTLE_DOOR_SENSOR)]
    try:
        bigDoorUp, littleDoorUp = d.getFeedback(commandList)
    except:
        return None
    else:
        return DoorState(bigDoorUp, littleDoorUp)

class LiftBotProtocol(RainBotProtocol):
    def connectionMade(self):
        print "LiftBot connected"
        initU3(self.d)
        powerOnOpener(self.d)
        self.doorState = getDoorState(self.d)
        if self.doorState:
            self.setStatus(str(self.doorState))
        self.updateLoop = LoopingCall(self.updateDoorState)               
        self.updateLoop.start(SAMPLE_PERIOD, now=False)

    def connectionLost(self, reason):
        print "LiftBot disconnected"
    
    def updateDoorState(self):
        newDoorState = getDoorState(self.d)
        if newDoorState and self.doorState != newDoorState:
            self.doorState = newDoorState
            self.setStatus(str(self.doorState))

    def onMessage(self, msg):
        #print "Got a message", msg.toXml()
        self.lastFrom = msg["from"] # Save this to send a reply.

        if msg["type"] == 'chat' and hasattr(msg, "body") and msg.body != None:
            msgTokens = str(msg.body).split()
            msgCommand = msgTokens[0].lower()
            if len(msgCommand) > 0:
                if msgCommand in ["1", "big", "b"]:
                    self.handleBig(msgTokens)
                elif msgCommand in ["2", "little", "l"]:
                    self.handleLittle(msgTokens)
                elif msgCommand == "help" or msgCommand == "h" or msgCommand == "?":
                    self.handleHelp(msgTokens)
                elif msgCommand == "quit" or msgCommand == "q":
                    self.handleQuit(msgTokens)
                else:
                    self.handleUnknownCommand(msgTokens)

    def handleBig(self, msgTokens):
        self.sendText("Pushing big button")
        self.pushAButton(pressBigDoorButton, releaseBigDoorButton)

    def handleLittle(self, msgTokens):
        self.sendText("Pushing little button")
        self.pushAButton(pressLittleDoorButton, releaseLittleDoorButton)

    def pushAButton(self, pressFunction, releaseFunction):
        if self.updateLoop.running:
            self.updateLoop.stop()
#        reactor.callLater(0, powerOnOpener, self.d)
        reactor.callLater(0, pressFunction, self.d)
        reactor.callLater(PUSH_TIME, releaseFunction, self.d)
#        reactor.callLater(PUSH_TIME + 2, powerOffOpener, self.d)
        if not self.updateLoop.running:
            reactor.callLater(PUSH_TIME + 3, self.updateLoop.start, SAMPLE_PERIOD)

    def handleHelp(self, msgTokens):
        responseText = "Commands:\n"
        responseText += "big (alias 'b' or '1'): Press big button\n"
        responseText += "little (alias 'l' or '2'): Press little button\n"
        responseText += "quit (alias 'q'): Quit the application\n"
        self.sendText(responseText)

    def handleQuit(self, msgTokens):
        """
        Exit. Hopefully you've got monit or something to start you back up.
        """
        responseText = "Quitting"
        self.sendText(responseText)
        reactor.callLater(1, reactor.stop)
