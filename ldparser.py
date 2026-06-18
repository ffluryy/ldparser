""" Parser for MoTec ld files

Code created through reverse engineering the data format.
"""

import datetime
import struct

import numpy as np


class ldData(object):
    """Container for parsed data of an ld file.

    Allows reading and writing.
    """

    def __init__(self, head, channs):
        self.head = head
        self.channs = channs

    def __getitem__(self, item):
        if not isinstance(item, int):
            col = [n for n, x in enumerate(self.channs) if x.name == item]
            if len(col) != 1:
                raise Exception("Could get column", item, col)
            item = col[0]
        return self.channs[item]

    def __iter__(self):
        return iter([x.name for x in self.channs])

    @classmethod
    def frompd(cls, df):
        # type: (pd.DataFrame) -> ldData
        """Create and ldData object from a pandas DataFrame.

        Example:
        import pandas as pd
        import numpy as np
        from ldparser import ldData

        # create test dataframe
        df = pd.DataFrame(np.random.randn(6,4),columns=list('ABCD'))
        print(df)
        # create an lddata object from the dataframe
        l = ldData.frompd(df)
        # write an .ld file
        l.write('/tmp/test.ld')

        # just to check, read back the file
        l = ldData.fromfile('/tmp/test.ld')
        # create pandas dataframe
        df = pd.DataFrame(data={c: l[c].data for c in l})
        print(df)

        """

        # for now, fix datatype and frequency
        freq, dtype = 10, np.float32

        # pointer to meta data of first channel
        meta_ptr = struct.calcsize(ldHead.fmt)

        # list of columns to read - only accept numeric data
        cols = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number)]

        # pointer to data of first channel
        chanheadsize = struct.calcsize(ldChan.fmt)
        data_ptr = meta_ptr + len(cols) * chanheadsize

        # create a mocked header
        head = ldHead(meta_ptr, data_ptr, 0,  None,
                       "testdriver",  "testvehicleid", "testvenue",
                       datetime.datetime.now(),
                       "just a test", "testevent", "practice")

        # create the channels, meta data and associated data
        channs, prev, next = [], 0, meta_ptr + chanheadsize
        for n, col in enumerate(cols):
            # create mocked channel header
            chan = ldChan(None,
                          meta_ptr, prev, next if n < len(cols)-1 else 0,
                          data_ptr, len(df[col]),
                          dtype, freq, 0, 1, 1, 0,
                          col, col, "m")

            # link data to the channel
            chan._data = df[col].to_numpy(dtype)

            # calculate pointers to the previous/next channel meta data
            prev = meta_ptr
            meta_ptr = next
            next += chanheadsize

            # increment data pointer for next channel
            data_ptr += chan._data.nbytes

            channs.append(chan)

        return cls(head, channs)

    @classmethod
    def fromfile(cls, f):
        # type: (str) -> ldData
        """Parse data of an ld file
        """
        return cls(*read_ldfile(f))

    def write(self, f):
        # type: (str) -> ()
        """Write an ld file containing the current header information and channel data
        """

        with open(f, 'wb') as f_:
            self.head.write(f_, len(self.channs))
            f_.seek(self.channs[0].meta_ptr)
            list(map(lambda c: c[1].write(f_, c[0]), enumerate(self.channs)))
            list(map(lambda c: f_.write(c.write_data()), self.channs))


class ldEvent(object):
    fmt = '<64s64s1024sH'

    def __init__(self, name, session, comment, venue_ptr, venue):
        self.name, self.session, self.comment, self.venue_ptr, self.venue = \
            name, session, comment, venue_ptr, venue

    @classmethod
    def fromfile(cls, f):
        # type: (file) -> ldEvent
        """Parses and stores the event information in an ld file
        """
        name, session, comment, venue_ptr = struct.unpack(
            ldEvent.fmt, f.read(struct.calcsize(ldEvent.fmt)))
        name, session, comment = map(decode_string, [name, session, comment])

        venue = None
        if venue_ptr > 0:
            f.seek(venue_ptr)
            venue = ldVenue.fromfile(f)

        return cls(name, session, comment, venue_ptr, venue)

    def write(self, f):
        f.write(struct.pack(ldEvent.fmt,
                            self.name.encode(),
                            self.session.encode(),
                            self.comment.encode(),
                            self.venue_ptr))

        if self.venue_ptr > 0:
            f.seek(self.venue_ptr)
            self.venue.write(f)

    def __str__(self):
        return "%s; venue: %s"%(self.name, self.venue)


class ldVenue(object):
    fmt = '<64s1034xH'

    def __init__(self, name, vehicle_ptr, vehicle):
        self.name, self.vehicle_ptr, self.vehicle = name, vehicle_ptr, vehicle

    @classmethod
    def fromfile(cls, f):
        # type: (file) -> ldVenue
        """Parses and stores the venue information in an ld file
        """
        name, vehicle_ptr = struct.unpack(ldVenue.fmt, f.read(struct.calcsize(ldVenue.fmt)))

        vehicle = None
        if vehicle_ptr > 0:
            f.seek(vehicle_ptr)
            vehicle = ldVehicle.fromfile(f)
        return cls(decode_string(name), vehicle_ptr, vehicle)

    def write(self, f):
        f.write(struct.pack(ldVenue.fmt, self.name.encode(), self.vehicle_ptr))

        if self.vehicle_ptr > 0:
            f.seek(self.vehicle_ptr)
            self.vehicle.write(f)

    def __str__(self):
        return "%s; vehicle: %s"%(self.name, self.vehicle)


class ldVehicle(object):
    fmt = '<64s128xI32s32s'

    def __init__(self, id, weight, type, comment):
        self.id, self.weight, self.type, self.comment = id, weight, type, comment

    @classmethod
    def fromfile(cls, f):
        # type: (file) -> ldVehicle
        """Parses and stores the vehicle information in an ld file
        """
        id, weight, type, comment = struct.unpack(ldVehicle.fmt, f.read(struct.calcsize(ldVehicle.fmt)))
        id, type, comment = map(decode_string, [id, type, comment])
        return cls(id, weight, type, comment)

    def write(self, f):
        f.write(struct.pack(ldVehicle.fmt, self.id.encode(), self.weight, self.type.encode(), self.comment.encode()))

    def __str__(self):
        return "%s (type: %s, weight: %i, %s)"%(self.id, self.type, self.weight, self.comment)


class ldHead(object):
    fmt = '<' + (
        "I4x"     # ldmarker
        "II"      # chann_meta_ptr chann_data_ptr
        "20x"     # ??
        "I"       # event_ptr
        "24x"     # ??
        "HHH"     # unknown static (?) numbers
        "I"       # device serial
        "8s"      # device type
        "H"       # device version
        "H"       # unknown static (?) number
        "I"       # num_channs
        "4x"      # ??
        "16s"     # date
        "16x"     # ??
        "16s"     # time
        "16x"     # ??
        "64s"     # driver
        "64s"     # vehicleid
        "64x"     # ??
        "64s"     # venue
        "64x"     # ??
        "1024x"   # ??
        "I"       # enable "pro logging" (some magic number?)
        "66x"     # ??
        "64s"     # short comment
        "126x"    # ??
        "64s"     # event
        "64s"     # session
    )

    def __init__(self, meta_ptr, data_ptr, aux_ptr, aux, driver, vehicleid, venue, datetime, short_comment, event, session):
        self.meta_ptr, self.data_ptr, self.aux_ptr, self.aux, self.driver, self.vehicleid, \
        self.venue, self.datetime, self.short_comment, self.event, self.session = meta_ptr, data_ptr, aux_ptr, aux, \
                                                driver, vehicleid, venue, datetime, short_comment, event, session

    @classmethod
    def fromfile(cls, f):
        # type: (file) -> ldHead
        """Parses and stores the header information of an ld file
        """
        (_, meta_ptr, data_ptr, aux_ptr,
            _, _, _,
            _, _, _, _, n,
            date, time,
            driver, vehicleid, venue,
            _, short_comment, event, session) = struct.unpack(ldHead.fmt, f.read(struct.calcsize(ldHead.fmt)))
        date, time, driver, vehicleid, venue, short_comment, event, session = \
            map(decode_string, [date, time, driver, vehicleid, venue, short_comment, event, session])

        try:
            # first, try to decode datatime with seconds
            _datetime = datetime.datetime.strptime(
                    '%s %s'%(date, time), '%d/%m/%Y %H:%M:%S')
        except ValueError:
            _datetime = datetime.datetime.strptime(
                '%s %s'%(date, time), '%d/%m/%Y %H:%M')

        aux = None
        if aux_ptr > 0:
            f.seek(aux_ptr)
            aux = ldEvent.fromfile(f)
        return cls(meta_ptr, data_ptr, aux_ptr, aux, driver, vehicleid, venue, _datetime, short_comment, event, session)

    def write(self, f, n):
        channel_counts = (n << 16) | n
        f.write(struct.pack(ldHead.fmt,
                            0x40,
                            self.meta_ptr, self.data_ptr, self.aux_ptr,
                            2, 0x4240, 0xf,
                            0x8540, "M1".encode(), 100, 0x80, channel_counts,
                            self.datetime.date().strftime("%d/%m/%Y").encode(),
                            self.datetime.time().strftime("%H:%M:%S").encode(),
                            self.driver.encode(), self.vehicleid.encode(), self.venue.encode(),
                            0x06344004, self.short_comment.encode(), self.event.encode(), self.session.encode(),
                            ))
        f.seek(0x5a)
        f.write(struct.pack("<HH", 200, 1))
        if self.aux_ptr > 0:
            f.seek(self.aux_ptr)
            self.aux.write(f)

    def __str__(self):
        return 'driver:    %s\n' \
               'vehicleid: %s\n' \
               'venue:     %s\n' \
               'event:     %s\n' \
               'session:   %s\n' \
               'short_comment: %s\n' \
               'event_long:    %s'%(
            self.driver, self.vehicleid, self.venue, self.event, self.session, self.short_comment, self.aux)


class ldChan(object):
    """Channel (meta) data

    Parses and stores the channel meta data of a channel in a ld file.
    Needs the pointer to the channel meta block in the ld file.
    The actual data is read on demand using the 'data' property.
    """

    fmt = '<' + (
        "IIII"    # prev_addr next_addr data_ptr n_data
        "H"       # some counter?
        "HHH"     # datatype datatype rec_freq
        "hhhh"    # shift mul scale unknown
        "32s"     # channel id/name
        "8s"      # display unit
        "8s"      # unknown
        "12s"     # unknown
        "f"       # display mode minimum
        "f"       # display mode maximum
        "B"       # decimal places
        "B"       # sampling mode
        "B"       # display format
        "13x"     # padding
        "II"      # channel metadata pointer, optional extra metadata pointer
    )
    fixed_size = struct.calcsize(fmt)
    default_metadata_size = 56
    # Display-unit bytes observed in exports/S1_#34112_20260403_142112_06.ld.
    # MoTeC i2 uses this 8-byte text field to bind a channel to its global
    # Data Properties quantity. Unitless channels use a null display-unit field.
    display_unit_lookup = {
        "": "0000000000000000",
        "%": "2500000000000000",
        "A": "4100000000000000",
        "A.h": "412e680000000000",
        "C": "4300000000000000",
        "G": "4700000000000000",
        "Hz": "487a000000000000",
        "N": "4e00000000000000",
        "Pa": "5061000000000000",
        "V": "5600000000000000",
        "deg": "6465670000000000",
        "deg/s": "6465672f73000000",
        "kPa": "6b50610000000000",
        "km": "6b6d000000000000",
        "km/h": "6b6d2f6800000000",
        "m": "6d00000000000000",
        "m/s": "6d2f730000000000",
        "m/s/s": "6d2f732f73000000",
        "mbar": "6d62617200000000",
        "mm": "6d6d000000000000",
        "ms": "6d73000000000000",
        "ohm": "6f686d0000000000",
        "ratio": "726174696f000000",
        "rpm": "72706d0000000000",
        "s": "7300000000000000",
        "us": "7573000000000000",
    }
    display_unit_lookup = {
        unit: bytes.fromhex(value)
        for unit, value in display_unit_lookup.items()
    }

    def __init__(self, _f, meta_ptr, prev_meta_ptr, next_meta_ptr, data_ptr, data_len,
                 dtype, freq, shift, mul, scale, dec,
                 name, short_name, unit, unknown=0, metadata_unknown=0, sample_mode=3,
                 display_format=0, unit_tail=None, display_min=0.0, display_max=0.0,
                 channel_metadata=None, extra_metadata=None):

        self._f = _f
        self.meta_ptr = meta_ptr
        self._data = None

        if unit_tail is None:
            unit_tail = b""
        if extra_metadata is None:
            extra_metadata = b""

        (self.prev_meta_ptr, self.next_meta_ptr, self.data_ptr, self.data_len,
        self.dtype, self.freq,
        self.shift, self.mul, self.scale, self.unknown, self.dec,
        self.name, self.short_name, self.unit, self.unit_tail, self.display_min,
        self.display_max, self.metadata_unknown, self.sample_mode,
        self.display_format, self.channel_metadata,
        self.extra_metadata) = prev_meta_ptr, next_meta_ptr, data_ptr, data_len,\
                                                 dtype, freq,\
                                                 shift, mul, scale, unknown, min(int(dec), 0x30),\
                                                 name, short_name, unit, unit_tail, display_min,\
                                                 display_max, metadata_unknown, sample_mode,\
                                                 display_format, channel_metadata, extra_metadata

    @classmethod
    def fromfile(cls, _f, meta_ptr, metadata_end=None):
        # type: (str, int) -> ldChan
        """Parses and stores the header information of an ld channel in a ld file
        """
        with open(_f, 'rb') as f:
            f.seek(meta_ptr)

            (prev_meta_ptr, next_meta_ptr, data_ptr, data_len, _,
             dtype_a, dtype, freq, shift, mul, scale, unknown,
             name, unit, short_name, unit_tail, display_min, display_max, dec, sample_mode, display_format,
             channel_metadata_ptr, extra_metadata_ptr) = \
                struct.unpack(ldChan.fmt, f.read(struct.calcsize(ldChan.fmt)))

            end_ptr = next_meta_ptr if next_meta_ptr else metadata_end
            channel_metadata = None
            extra_metadata = b""
            if channel_metadata_ptr:
                channel_metadata_end = extra_metadata_ptr if extra_metadata_ptr else end_ptr
                if channel_metadata_end and channel_metadata_end >= channel_metadata_ptr:
                    f.seek(channel_metadata_ptr)
                    channel_metadata = f.read(channel_metadata_end - channel_metadata_ptr)
            if extra_metadata_ptr and end_ptr and end_ptr >= extra_metadata_ptr:
                f.seek(extra_metadata_ptr)
                extra_metadata = f.read(end_ptr - extra_metadata_ptr)

        name, short_name, unit = map(decode_string, [name, short_name, unit])

        if dtype_a in [0x07]:
            dtype = [None, np.float16, None, np.float32][dtype-1]
        elif dtype_a == 0x06:
            dtype = np.int32
        elif dtype_a in [0, 0x03, 0x05]:
            dtype = [None, np.int16, None, np.int32][dtype-1]
        else: raise Exception('Datatype %i not recognized'%dtype_a)

        return cls(_f, meta_ptr, prev_meta_ptr, next_meta_ptr, data_ptr, data_len,
                   dtype, freq, shift, mul, scale, dec, name, short_name, unit,
                   unknown, 0, sample_mode, display_format, unit_tail,
                   display_min, display_max, channel_metadata, extra_metadata)

    def metadata_size(self):
        return self.fixed_size + len(self.get_channel_metadata()) + len(self.extra_metadata)

    def get_channel_metadata(self):
        if self.channel_metadata is not None:
            return self.channel_metadata

        metadata_ptr = self.meta_ptr + self.fixed_size
        pointer_value = metadata_ptr + 44
        rate_hint = max(1, int(round(self.freq * 5.0 / 6.0)))
        return struct.pack("<HHII36xHHI", 0, self.freq, 2, pointer_value, 1, rate_hint, 0)

    def get_display_unit(self):
        unit = self.unit
        if isinstance(unit, bytes):
            unit = decode_string(unit)

        if unit in self.display_unit_lookup:
            return self.display_unit_lookup[unit]

        return str(unit).encode()[:8].ljust(8, b"\0")

    def write(self, f, n):
        if self.dtype == np.float16 or self.dtype == np.float32:
            dtype_a = 0x07
            dtype = {np.float16: 2, np.float32: 4}[self.dtype]
        else:
            dtype_a = 0x03
            dtype = {np.int16: 2, np.int32: 4}[self.dtype]

        channel_metadata = self.get_channel_metadata()
        channel_metadata_ptr = self.meta_ptr + self.fixed_size if channel_metadata else 0
        extra_metadata_ptr = channel_metadata_ptr + len(channel_metadata) if self.extra_metadata else 0
        display_unit = self.get_display_unit()

        f.write(struct.pack(ldChan.fmt,
                            self.prev_meta_ptr, self.next_meta_ptr, self.data_ptr, self.data_len,
                            0x2ee1+n, dtype_a, dtype, self.freq, self.shift, self.mul, self.scale, self.unknown,
                            self.name.encode(), display_unit, self.short_name.encode(), self.unit_tail,
                            self.display_min, self.display_max, min(int(self.dec), 0x30),
                            self.sample_mode, self.display_format, channel_metadata_ptr, extra_metadata_ptr))
        f.write(channel_metadata)
        f.write(self.extra_metadata)

    def write_data(self):
        return np.asarray(self.data, dtype=self.dtype).tobytes()

    @property
    def data(self):
        # type: () -> np.array
        """ Read the data words of the channel
        """
        if self._data is None:
            # jump to data and read
            with open(self._f, 'rb') as f:
                f.seek(self.data_ptr)
                try:
                    self._data = np.fromfile(f,
                                            count=self.data_len, dtype=self.dtype)

                    if len(self._data) != self.data_len:
                        raise ValueError("Not all data read!")

                except ValueError as v:
                    print(v, self.name, self.freq,
                          hex(self.data_ptr), hex(self.data_len),
                          hex(len(self._data)),hex(f.tell()))
                    # raise v
        return self._data

    def __str__(self):
        return 'chan %s (%s) [%s], %i Hz'%(
            self.name,
            self.short_name, self.unit,
            self.freq)


def decode_string(bytes):
    # type: (bytes) -> str
    """decode the bytes and remove trailing zeros
    """
    try:
        return bytes.decode('ascii').strip().rstrip('\0').strip()
    except Exception as e:
        print("Could not decode string: %s - %s"%(e, bytes))
        return ""
        # raise e

def read_channels(f_, meta_ptr, metadata_end=None):
    # type: (str, int) -> list
    """ Read channel data inside ld file

    Cycles through the channels inside an ld file,
     starting with the one where meta_ptr points to.
     Returns a list of ldchan objects.
    """
    chans = []
    while meta_ptr:
        chan_ = ldChan.fromfile(f_, meta_ptr, metadata_end)
        chans.append(chan_)
        meta_ptr = chan_.next_meta_ptr
    return chans


def read_ldfile(f_):
    # type: (str) -> (ldHead, list)
    """ Read an ld file, return header and list of channels
    """
    head_ = ldHead.fromfile(open(f_,'rb'))
    chans = read_channels(f_, head_.meta_ptr, head_.data_ptr)
    return head_, chans


if __name__ == '__main__':
    """ Small test of the parser.
    
    Decodes all ld files in the directory. For each file, creates 
    a plot for data with the same sample frequency.  
    """

    import sys, os, glob
    from itertools import groupby
    import pandas as pd
    import matplotlib.pyplot as plt

    if len(sys.argv)!=2:
        print("Usage: ldparser.py /some/path/")
        exit(1)

    for f in glob.glob('%s/*.ld'%sys.argv[1]):
        print(os.path.basename(f))

        l = ldData.fromfile(f)
        print(l.head)
        print(list(map(str, l)))
        print()

        # create plots for all channels with the same frequency
        for f, g in groupby(l.channs, lambda x:x.freq):
            df = pd.DataFrame({i.name.lower(): i.data for i in g})
            df.plot()
            plt.show()
