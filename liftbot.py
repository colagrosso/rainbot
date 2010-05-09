from twisted.words.xish import domish
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from wokkel.xmppim import MessageProtocol, AvailablePresence

from rainbot import RainBotProtocol
import u3

BIG_DOOR_BUTTON    = 4
BIG_DOOR_SENSOR    = 7
LITTLE_DOOR_BUTTON = 5
LITTLE_DOOR_SENSOR = 6

SAMPLE_PERIOD = 1

PUSH_TIME = 2 # Seconds to hold the button down for

# Set buttons for digital output low and sensors for digital input
# Also set DAC0 to 0 V
INIT_IO_COMMAND = [u3.BitDirWrite(BIG_DOOR_BUTTON, 1),
                   u3.BitDirWrite(LITTLE_DOOR_BUTTON, 1),
                   u3.BitStateWrite(BIG_DOOR_BUTTON, 0),
                   u3.BitStateWrite(LITTLE_DOOR_BUTTON, 0),
                   u3.BitDirWrite(BIG_DOOR_SENSOR, 0),
                   u3.BitDirWrite(BIG_DOOR_SENSOR, 0),
                   u3.DAC0_16(0)
                  ]

def initU3(d):
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
    """Set BIG_DOOR_BUTTON output high."""
    commandList = [u3.BitDirWrite(BIG_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(BIG_DOOR_BUTTON, 1)]
    d.getFeedback(commandList)
    
def releaseBigDoorButton(d):
    """Set BIG_DOOR_BUTTON output low."""
    commandList = [u3.BitDirWrite(BIG_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(BIG_DOOR_BUTTON, 0)]
    d.getFeedback(commandList)

def pressLittleDoorButton(d):
    """Set LITTLE_DOOR_BUTTON output high."""
    commandList = [u3.BitDirWrite(LITTLE_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(LITTLE_DOOR_BUTTON, 1)]
    d.getFeedback(commandList)

def releaseLittleDoorButton(d):
    """Set LITTLE_DOOR_BUTTON output low."""
    commandList = [u3.BitDirWrite(LITTLE_DOOR_BUTTON, 1), 
                   u3.BitStateWrite(LITTLE_DOOR_BUTTON, 0)]
    d.getFeedback(commandList)

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
    bigDoorUp, littleDoorUp = d.getFeedback(commandList)
    return DoorState(bigDoorUp, littleDoorUp)

class LiftBotProtocol(RainBotProtocol):
    def connectionMade(self):
        print "LiftBot connected"
        initU3(self.d)
        self.doorState = getDoorState(self.d)
        self.setStatus(str(self.doorState))
        self.updateLoop = LoopingCall(self.updateDoorState)               
        self.updateLoop.start(SAMPLE_PERIOD, now=False)

    def connectionLost(self, reason):
        print "LiftBot disconnected"
    
    def updateDoorState(self):
        newDoorState = getDoorState(self.d)
        if self.doorState != newDoorState:
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
                else:
                    self.handleUnknownCommand(msgTokens)

    def handleBig(self, msgTokens):
        self.sendText("Pushing big button")
        reactor.callLater(0, powerOnOpener, self.d)
        reactor.callLater(1, pressBigDoorButton, self.d)
        reactor.callLater(PUSH_TIME + 1, releaseBigDoorButton, self.d)
        reactor.callLater(PUSH_TIME + 2, powerOffOpener, self.d)

    def handleLittle(self, msgTokens):
        self.sendText("Pushing little button")
        reactor.callLater(0, powerOnOpener, self.d)
        reactor.callLater(1, pressLittleDoorButton, self.d)
        reactor.callLater(PUSH_TIME + 1, releaseLittleDoorButton, self.d)
        reactor.callLater(PUSH_TIME + 2, powerOffOpener, self.d)

    def handleHelp(self, msgTokens):
        responseText = "Commands:\n"
        responseText += "big (alias 'b' or '1'): Press big button\n"
        responseText += "little (alias 'l' or '2'): Press little button\n"
        self.sendText(responseText)
