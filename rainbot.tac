from twisted.application import service
from twisted.words.protocols.jabber import jid
from wokkel.client import XMPPClient

from rainbot import RainBotProtocol, Scheduler, ALL_OFF_COMMAND

application = service.Application("rainbot")

import u3
d = u3.U3()
d.getFeedback(ALL_OFF_COMMAND)

YOUR_JID  = ""
YOUR_PASS = ""

xmppclient = XMPPClient(jid.internJID(YOUR_JID), YOUR_PASS)
xmppclient.logTraffic = False
rainbot = RainBotProtocol()
rainbot.d = d

rainbot.setHandlerParent(xmppclient)
xmppclient.setServiceParent(application)