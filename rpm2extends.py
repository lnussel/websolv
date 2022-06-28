#!/usr/bin/python3
# Copyright (c) 2016,2022 SUSE LLC
# Author: Ludwig Nussel
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

import argparse
import logging
import os
import re
import stat
import struct
import sys
import mmap
import zstandard
import pathlib
import bz2
import gzip

from pprint import pprint

from CpioReader import CpioFile

# XXX: sysconf(_SC_PAGESIZE)
PAGE_SIZE = 4096

RPMTAG_NAME                 = 1000
RPMTAG_FILESIZES            = 1028
RPMTAG_FILEMODES            = 1030
RPMTAG_FILEFLAGS            = 1037
RPMTAG_FILEINODES           = 1096
RPMTAG_BASENAMES            = 1117
RPMTAG_DIRINDEXES           = 1116
RPMTAG_DIRNAMES             = 1118
RPMTAG_PAYLOADFORMAT        = 1124
RPMTAG_PAYLOADCOMPRESSOR    = 1125
RPMTAG_FILENLINKS           = 5045

RPMFILE_GHOST               = (1 << 6)

def main(args):

    # do some work here
    logger = logging.getLogger("rpm2extends")

    for fn in args.file:
        with open(fn, "r+b") as fh:
            (magic, sigtype) = struct.unpack('>I74xH16x', fh.read(96))
            if magic != 0xedabeedb or sigtype != 5:
                raise Exception("invalid lead: {:x}/{:x}".format(magic, sigtype))

            logger.debug("parse signature header")

            (hm1,hm2) = struct.unpack('>II', fh.read(8))
            if hm1 != 0x8eade801 or hm2 != 0:
                raise Exception("invalid header magic {:x}{:x}".format(hm1, hm2))

            (cnt, cntdata) = struct.unpack('>II', fh.read(8));
            if cnt >= 1048576 or cntdata >= 33554432:
                raise Exception("invalid header {:x} {:x}".format(cnt, cntdata))

            logger.debug("index area cnt {} data {}".format(cnt, cntdata))

            # just skip over it for now. We may want to remove payload digests
            # here in the future
            fh.seek(cnt*16, os.SEEK_CUR)
            fh.seek(cntdata, os.SEEK_CUR)
            fh.seek(8-(cntdata & 7), os.SEEK_CUR)

            logger.debug("parse header")

            (hm1, hm2) = struct.unpack('>II', fh.read(8))
            if hm1 != 0x8eade801 or hm2 != 0:
                raise Exception("invalid header magic {:x}{:x}".format(hm1, hm2))

            (cnt, cntdata) = struct.unpack('>II', fh.read(8))
            if cnt >= 1048576 or cntdata >= 33554432:
                raise Exception("invalid header {:x} {:x}".format(cnt, cntdata))

            tags = dict()
            while cnt > 0:
                (tag, tagtype, offset, count) = struct.unpack('>4I', fh.read(16));
                logger.debug("tag %d %d %d %d", tag, tagtype, offset, count)
                if tag in (RPMTAG_NAME, RPMTAG_PAYLOADFORMAT,
                           RPMTAG_PAYLOADCOMPRESSOR, RPMTAG_BASENAMES,
                           RPMTAG_DIRNAMES, RPMTAG_DIRINDEXES,
                           RPMTAG_FILEINODES, RPMTAG_FILENLINKS,
                           RPMTAG_FILESIZES, RPMTAG_FILEFLAGS,
                           RPMTAG_FILEMODES):
                    if (tagtype == 6 and count == 1) \
                            or tagtype == 8 \
                            or tagtype == 4 \
                            or tagtype == 3:
                        tags[tag] = (tagtype, offset, count)
                    else:
                        raise Exception("{}: tag type {}, count {} not supported".format(tag, tagtype, count))
                cnt -= 1

            datastart = fh.tell()

            for tag in sorted(tags.keys()):
                (tagtype, o, count) = tags[tag]
                if o >= cntdata:
                    raise Exception("invalid offset for %d: %d".format(tag, o))
                fh.seek(datastart+o, os.SEEK_SET)
                if tagtype == 6 or tagtype == 8:  # strings
                    if (tagtype) == 8:
                        tags[tag] = []
                    while count:
                        value = b''
                        b = fh.read(1)
                        while b != b'\x00' and fh.tell() < datastart + cntdata:
                            value += b
                            b = fh.read(1)
                        # logger.info("%s %d %s", fn, tag, value.decode())
                        if (tagtype) == 6:
                            tags[tag] = value.decode()
                        else:
                            tags[tag].append(value.decode())
                        count -= 1
                elif tagtype == 3:  # int16
                    tags[tag] = struct.unpack('>{}H'.format(count), fh.read(count*2))
                elif tagtype == 4:  # int32
                    tags[tag] = struct.unpack('>{}I'.format(count), fh.read(count*4))


            if tags[RPMTAG_PAYLOADCOMPRESSOR] not in ('zstd', 'bzip2', 'gzip') \
                    or tags[RPMTAG_PAYLOADFORMAT] != 'cpio':
                raise Exception("{}: unsupported payload {}.{}".format(tags[RPMTAG_NAME], tags[RPMTAG_PAYLOADFORMAT], tags[RPMTAG_PAYLOADCOMPRESSOR]))

            ofn = os.path.join(args.output, os.path.basename(fn))
            ofh = open(ofn, 'w+b')
            fh.seek(0, os.SEEK_SET)
            ofh.write(fh.read(datastart+cntdata))
            # marker XXX: add another rpm header instead or add tag
            # to signature header?
            ofh.write(struct.pack('>I', 12245589))
            # pad to page size
            left = ofh.tell()&(PAGE_SIZE-1)
            if left:
                ofh.seek(PAGE_SIZE - left, os.SEEK_CUR)

            logger.debug("start at %d", ofh.tell())

            # contains no files
            if RPMTAG_BASENAMES not in tags:
                ofh.truncate(ofh.tell())
                continue

            # jump to payload
            fh.seek(datastart + cntdata, os.SEEK_SET)

            if tags[RPMTAG_PAYLOADCOMPRESSOR] == 'zstd':
                (compmagic,) = struct.unpack('>I', fh.read(4))
                logger.debug("payload starts with %x", compmagic)
                if compmagic != 0x28b52ffd:
                    raise Exception("only zstd supported")

                dctx = zstandard.ZstdDecompressor()
                reader = dctx.stream_reader(fh)
            elif tags[RPMTAG_PAYLOADCOMPRESSOR] == 'bzip2':
                (compmagic,) = struct.unpack('3s', fh.read(3))
                logger.debug("payload starts with %s", compmagic)
                if compmagic != b'BZh':
                    raise Exception("invalid magic {}".format(compmagic))
                reader = bz2.BZ2File(fh, 'r')
            elif tags[RPMTAG_PAYLOADCOMPRESSOR] == 'gzip':
                (compmagic,) = struct.unpack('>H', fh.read(2))
                logger.debug("payload starts with %s", compmagic)
                if compmagic != 0x1f8b:
                    raise Exception("invalid magic {}".format(compmagic))
                reader = gzip.GzipFile(fileobj=fh, mode='r')

            # rewind compressor detection
            fh.seek(datastart + cntdata, os.SEEK_SET)

            odatastart = ofh.tell()

            # calculate offset for each file based on inode. Files
            # with same inode are hardlinks
            inodes = dict()
            offset = 0
            maxoffset = 0
            for i, inode in enumerate(tags[RPMTAG_FILEINODES]):
                if inode in inodes:
                    logger.debug("skip hardlink %s inode %d at fi %s",
                                 tags[RPMTAG_BASENAMES][i], inode, i)
                    continue
                if not stat.S_ISREG(tags[RPMTAG_FILEMODES][i]):
                    continue
                size = tags[RPMTAG_FILESIZES][i]
                if size == 0:
                    continue
                flags = tags[RPMTAG_FILEFLAGS][i]
                if flags & RPMFILE_GHOST:
                    continue

                logger.debug("%s inode %d at offset %s",
                             tags[RPMTAG_BASENAMES][i],
                             inode, odatastart + offset)
                inodes[inode] = offset
                if offset > maxoffset:
                    maxoffset = offset
                offset += size
                # pad to page size
                left = size & (PAGE_SIZE-1)
                if left:
                    offset += PAGE_SIZE - left

            offset = 0
            while True:
                with CpioFile(reader) as cpio:
                    if cpio.last():
                        break
                    if not stat.S_ISREG(cpio.c_mode):
                        #logger.debug("{} skipped".format(cpio.name))
                        cpio.read()
                        continue
                    if cpio.c_filesize == 0:
                        #logger.debug("{} size is zero, skipped".format(cpio.name))
                        cpio.read()
                        continue
                    if cpio.c_ino not in inodes:
                        raise Exception("file {} not found in inode table".format(cpio.name.decode()))
                    offset = inodes[cpio.c_ino]
                    logger.debug("adding %s with inode %d at %d %d",
                                 cpio.name.decode(), cpio.c_ino,
                                 odatastart + offset, cpio.c_filesize)
                    ofh.seek(odatastart + offset, os.SEEK_SET)
                    ofh.write(cpio.read())
                    # make sure last file end at page size
                    if offset == maxoffset:
                        left = ofh.tell() & (PAGE_SIZE-1)
                        if left:
                            logger.debug("add extra %s bytes",
                                         PAGE_SIZE - left)
                            ofh.truncate(ofh.tell() + PAGE_SIZE - left)

            logger.info("wrote %s", ofn)

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                        description='boilerplate python commmand line program')
    parser.add_argument("--dry", action="store_true", help="dry run")
    parser.add_argument("--debug", action="store_true", help="debug output")
    parser.add_argument("--verbose", action="store_true", help="verbose")
    parser.add_argument("--output", help="output directory", required=True)
    parser.add_argument("file", nargs='*', help="some file name")

    args = parser.parse_args()

    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = None

    logging.basicConfig(level=level)

    sys.exit(main(args))

# vim: sw=4 et
