#!/usr/bin/python3
# Copyright (c) 2021 SUSE LLC
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import struct
import os

class CpioFile:
    def __init__(self, fh):
        self.fh = fh
        self.name = None

    def __enter__(self):
        if (self.fh.tell() & 3):
            raise Exception("invalid offset %d" % self.fh.tell())

        fmt = "6s8s8s8s8s8s8s8s8s8s8s8s8s8s"

        fields = struct.unpack(fmt, self.fh.read(struct.calcsize(fmt)))

        if fields[0] != b"070701":
            raise Exception("invalid cpio header %s" % fields[0])

        names = ("c_ino", "c_mode", "c_uid", "c_gid",
                 "c_nlink", "c_mtime", "c_filesize",
                 "c_devmajor", "c_devminor", "c_rdevmajor",
                 "c_rdevminor", "c_namesize", "c_check")
        for (n, v) in zip(names, fields[1:]):
            setattr(self, n, int(v, 16))

        self.name = struct.unpack('%ds' % (self.c_namesize - 1), self.fh.read(self.c_namesize - 1))[0]
        self.fh.read(1)  # \0
        if (self.c_namesize+2) % 4:
            self.fh.read(4 - (self.c_namesize+2) % 4)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            return None
        if self.c_filesize % 4:
            self.fh.read(4 - self.c_filesize % 4)

    def last(self):
        return self.name == b'TRAILER!!!'

    def __str__(self):
        return "[%s %d]" % (self.name, self.c_filesize)

    def read(self):
        return self.fh.read(self.c_filesize)

class CpioReader:
    def __init__(self, fh = None, fn = None):
        if fh is not None:
            self.fh = fh
        elif fn is not None:
            self.fh = open(fn, 'rb')

    def extract(self, outdir):

        while True:
            with CpioFile(self.fh) as f:
                if f.last():
                    break
                with open(os.path.join(outdir if outdir else '.', os.path.basename(f.name)), 'wb') as ofh:
                    ofh.write(f.read())


if __name__ == '__main__':
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option("--debug", action="store_true", help="debug output")
    parser.add_option("--verbose", action="store_true", help="verbose")
    parser.add_option("--outdir", metavar="DIR", help="where to put files")

    (options, args) = parser.parse_args()

    for fn in args:
        cpio = CpioReader(fn)
        cpio.extract(options.outdir)
