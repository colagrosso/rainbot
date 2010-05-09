from twisted.application import service
from twisted.words.protocols.jabber import jid
from wokkel.client import XMPPClient

from rainbot import RainBotProtocol, Scheduler, ALL_OFF_COMMAND
from moisture import MoistureSampler
from liftbot import LiftBotProtocol

application = service.Application("rainbot")

import u3
d = u3.U3()
d.getFeedback(ALL_OFF_COMMAND)

YOUR_JID  = ""
YOUR_PASS = ""
LIFTBOT_JID  = ""
LIFTBOT_PASS = ""

xmppclient = XMPPClient(jid.internJID(YOUR_JID), YOUR_PASS)
xmppclient.logTraffic = False
rainbot = RainBotProtocol()
rainbot.d = d

MOISTURE_REGISTER = 0
moisture = MoistureSampler(d, MOISTURE_REGISTER)

rainbot.moisture = moisture

rainbot.setHandlerParent(xmppclient)
xmppclient.setServiceParent(application)

liftBot_xmppclient = XMPPClient(jid.internJID(LIFTBOT_JID), LIFTBOT_PASS)
liftBot_xmppclient.logTraffic = False
liftbot = LiftBotProtocol()
liftbot.d = d

liftbot.setHandlerParent(liftBot_xmppclient)
liftBot_xmppclient.setServiceParent(application)
