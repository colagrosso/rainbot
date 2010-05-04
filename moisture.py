from twisted.internet.task import LoopingCall
import rrdtool

SAMPLE_PERIOD = 300         # Every 5 minutes
RRD_NAME = "moisture.rrd"

class MoistureSampler(object):
    """
    An instance of this class samples, records, and reports moisture readings.
    """
    def __init__(self, device, sensorRegister):
        self.device = device
        self.sensorRegister = sensorRegister
        self.sampleLoop = LoopingCall(self.sampleAndLog)               
        self.sampleLoop.start(SAMPLE_PERIOD, now=False)
        self.checkRRD()
    
    def checkRRD(self):
        """
        Checks for RRD_NAME, creating it if necessary.
        """
        import os
        try:
            os.stat(RRD_NAME)
        except OSError:
            self.createRRD()
    
    def createRRD(self):
        """
        Creates an RRD with these RRAs:
            Hourly (all 12 readings)
            Daily
            Weekly
            Monthly (6-hour summaries)
            Yearly
            
        Note: Sensor range is 0-1.8 V
        """
        print "Creating database", RRD_NAME
        rrdtool.create(RRD_NAME,
                       "--step", str(SAMPLE_PERIOD),
                       "DS:moisture:GAUGE:%s:0:1.8" % (str(2*SAMPLE_PERIOD),),
                       "RRA:AVERAGE:0.5:1:12",
                       "RRA:AVERAGE:0.5:12:24",
                       "RRA:AVERAGE:0.5:12:168",
                       "RRA:AVERAGE:0.5:72:120",
                       "RRA:AVERAGE:0.5:288:365")

    def sampleAndLog(self):
        reading = self.device.readRegister(self.sensorRegister)
        rrdtool.update(RRD_NAME,
                       "N:" + str(reading))

    def fetchAverage(self):
        return rrdtool.fetch(RRD_NAME, "AVERAGE")
