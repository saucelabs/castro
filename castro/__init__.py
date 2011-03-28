import os
import tempfile
from datetime import datetime, timedelta
from sys import stdout
from time import sleep

from multiprocessing import Process
import yaml

import lib.messageboard as mb
from lib.pyvnc2swf import vnc2swf

# Get directory for storing files:
DATA_DIR = os.environ.get('CASTRO_DATA_DIR') or tempfile.gettempdir()

class CastroException(Exception):
    pass

class Castro:
    def __init__(self,
                 filename = "castro-video.swf",
                 host     = "localhost",
                 display  = 0,
                 framerate = 12,
                 freq = 1,
                 clipping = None,
                 port = None,
                 passwd = os.path.join(os.path.expanduser("~"),
                                       ".vnc", "passwd"),
                 h264 = False,
                 seconds_per_keyframe = 5):
        self.filename = filename
        self.filepath = os.path.join(DATA_DIR, self.filename)
        self.host = host
        self.display = display
        self.framerate = framerate
        self.clipping = clipping
        self.passwd = passwd
        self.port = port
        self.freq = freq
        self.h264 = h264
        self.seconds_per_keyframe = seconds_per_keyframe

        # Post-process data:
        self.duration = 0
        self.tempfilepath = os.path.join(DATA_DIR, 'temp-' + self.filename)
        self.cuefilepath = os.path.join(DATA_DIR, self.filename + "-cuepoints.xml")

        # Finally...
        self.init()

    def init(self):
        args=['lib/pyvnc2swf/vnc2swf.py',
               '-n',
               '-o', self.filepath,
               '-R', 3,
               '%s:%s' % (self.host, self.display) ]

        # If password file is specified, insert it into args
        if self.passwd:
            args.insert(4, '-P')
            args.insert(5, self.passwd)

        # If framerate is specified, insert it into args
        if self.framerate:
            args.insert(4, '-r')
            args.insert(5, self.framerate)

        # If clipping is specified, insert it into args
        if self.clipping:
            args.insert(4, '-C')
            args.insert(5, self.clipping)

        if self.port:
            args.append(str(self.port))

        self.recorder = Process(target= vnc2swf.main, args=[args])

    def start(self):
        self.recorder.start()

    def flag_for_stop(self):
        mb.recording_should_continue.write(False)

    def stop(self):
        self.flag_for_stop()
        self.recorder.join(timeout=90)
        if self.recorder.is_alive():
            self.recorder.terminate()
            self.recorder.join()

    def restart(self):
        self.stop()
        self.init()
        self.start()

    def process(self):
        self.encode()
        self.calc_duration()
        self.cuepoint()
        self.inject_metadata()
        self.cleanup()

    def encode(self):
        """
        Note: The output *needs* to have a different name than the original
        The tip for adding the "-g" flag: http://www.infinitecube.com/?p=9
        """

        print "Running ffmpeg: encoding and creating keyframes"
        cmd = "ffmpeg -y -i %s -g %s -sameq %s"
        if self.h264:
            cmd = "ffmpeg -y -i %s -vcodec libx264 -coder 0 -flags -loop -cmp +chroma -partitions -parti8x8-parti4x4-partp8x8-partb8x8 -me_method dia -subq 0 -me_range 16 -g %s -keyint_min 25 -sc_threshold 0 -i_qfactor 0.71 -b_strategy 0 -qcomp 0.6 -qmin 10 -qmax 51 -qdiff 4 -bf 0 -refs 1 -directpred 1 -trellis 0 -flags2 -bpyramid-mixed_refs-wpred-dct8x8+fastpskip-mbtree -wpredp 0 -aq_mode 0 -crf 30 %s"

        os.system(cmd % (self.filepath,
                         self.framerate * self.seconds_per_keyframe,
                         self.tempfilepath))

    def calc_duration(self):
        print "Getting Duration:"
        flv_data_raw = os.popen("flvtool2 -P %s" % self.tempfilepath).read()
        flv_data = yaml.load(flv_data_raw)
        if type(flv_data) != dict:
            raise CastroException("Invalid FLV metadata: %s", flv_data_raw)
        self.duration = int(round(flv_data[flv_data.keys()[0]]['duration']))
        print "Duration: %s" % self.duration

    def cuepoint(self):
        print "\n\nCreating cuepoints:"
        # Create the cuepoints file
        cuefile = open(self.cuefilepath,'w')

        # Write the header
        cuefile.write ("<?xml version=\"1.0\"?>\n")
        cuefile.write ("<tags>\n")
        cuefile.write ("  <!-- navigation cue points -->\n")

        # Write the body
        for i in range(0,self.duration,self.freq):
            name = (datetime(1900,1,1,0,0,0) + timedelta(seconds=i)).strftime('%H:%M:%S')
            cuefile.write ("  <metatag event=\"onCuePoint\">\n")
            cuefile.write ("    <name>%s</name>\n" % name)
            cuefile.write ("    <timestamp>%s000</timestamp>\n" % i)
            cuefile.write ("    <type>navigation</type>\n")
            cuefile.write ("  </metatag>\n")


        # Write the footer
        cuefile.write ("</tags>\n")
        cuefile.close()

    def inject_metadata(self):
        os.system("flvtool2 -AUt %s %s %s" %
            (self.cuefilepath,
             self.tempfilepath,
             self.filepath))

    def cleanup(self):
        os.remove(self.cuefilepath)
        os.remove(self.tempfilepath)


# To be used with a "with" statement
class video:
    def __init__(self, *args, **kwargs):
        self.recorder = Castro(*args, **kwargs)

    def __enter__(self):
        self.recorder.start()

    def __exit__(self, type, value, traceback):
        self.recorder.stop()

# Show some output on screen during a test
def countdown_timer():
    stdout.write("\nRecording a 10 second video...\n\n")
    for i in range(10,0,-1):
        stdout.write("%s " % i)
        stdout.flush()
        sleep(1)
    stdout.write("\n")

def test():
    c = Castro()
    c.init()
    c.start()
    countdown_timer()
    c.stop()

if __name__ == '__main__':
    test()
