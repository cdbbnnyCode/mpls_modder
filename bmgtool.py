from gclib import fs_helpers as fs
import io
import struct
import sys
import re

def bytestr(data):
    return "".join(["{:02x}".format(x) for x in data])

class MESGEntry:
    def __init__(self, string, info, m_id):
        self.string = string
        self.info = info
        self.m_id = m_id

    def __str__(self):
        if self.m_id < 0:
            return "x;{}; {}".format(bytestr(self.info), self.string)
        else:
            return "{};{}; {}".format(self.m_id, bytestr(self.info), self.string)

def read_escape(data, off):
    esc_len = fs.read_u8(data, off)
    esc_grp = fs.read_u8(data, off+1)
    esc_num = fs.read_u16(data, off+2)
    esc_data = fs.read_bytes(data, off+4, esc_len-6)

    esc_str = "{" + "{:02x}:{:04x}".format(esc_grp, esc_num)
    if len(esc_data) > 0:
        esc_str += ":" + bytestr(esc_data)
    esc_str += "}"

    return off+esc_len-2, esc_str

def parse_esc_str(esc_str):
    fields = esc_str.split(':')
    if len(fields) == 2:
        fields = [fields[0], fields[1], ""]
    assert len(fields[0]) == 2
    assert len(fields[1]) == 4
    assert (len(fields[2]) % 4) == 0
    esc_grp = int(fields[0], 16)
    esc_num = int(fields[1], 16)
    esc_data = bytearray()
    for i in range(len(fields[2]) // 2):
        esc_data.append(int(fields[2][i*2:i*2+2], 16))
    esc_len = 6 + len(esc_data)
    return b'\x00\x1a' + struct.pack('>BBH', esc_len, esc_grp, esc_num) + bytes(esc_data)

def read_utf16(data, off):
    end = off
    s = ""
    c = b'' # binary char data (2-4 bytes)
    while True:
        curr_char = fs.read_bytes(data, end, 2)
        cv, = struct.unpack(">H", curr_char)
        if cv == 0:
            break
        elif cv >= 0xd800 and cv < 0xe000:
            # utf-16 surrogate
            c += curr_char
            end += 2
        else:
            c += curr_char
            c_dec = c.decode('utf-16be')
            c = b''
            if c_dec == '\x1a':
                # escape
                end, esc_str = read_escape(data, end+2)
                s += esc_str
            elif c_dec in ['{', '}', '\\']:
                # bracket characters need to be escaped
                s += '\\' + c_dec
                end += 2
            elif c_dec == '\n':
                # newlines delimit strings so we need to escape them
                s += '\\n'
                end += 2
            else:
                s += c_dec
                end += 2 
    return s

def encode_utf16(s):
    p = 0
    out = b''
    while p < len(s):
        c = s[p]
        if c == '\\':
            c = s[p+1]
            if c == 'n':
                out += "\n".encode('utf-16be')
            else:
                out += c.encode('utf-16be')
            p += 2
        elif c == '{':
            esc = s[p+1:]
            esc = esc[:esc.index('}')]
            out += parse_esc_str(esc)
            p += len(esc) + 2
        else:
            out += c.encode('utf-16be')
            p += 1
    # add null terminator
    out += b'\0\0'
    return out

class MESGFile:
    def __init__(self):
        # encodings -- according to https://wiki.tockdom.com/wiki/BMG_(File_Format)
        # 0: old GC format
        # 1: CP-1252
        # 2: UTF-16 (most common)
        # 3: Shift-JIS
        # 4: UTF-8
        # we will only support UTF-16
        self.encoding = 2 
        self.inf_entry_size = 0
        self.has_mid1 = False
        self.entries = []

    def read(self, data):
        magic = fs.read_bytes(data, 0, 8)
        assert magic == b"MESGbmg1"
        sections = fs.read_u32(data, 0xc)
        self.encoding = fs.read_u8(data, 0x10)

        off = 0x20
        inf1_entries = []
        dat1_data = None
        mid1_entries = []
        for i in range(sections):
            secname = fs.read_bytes(data, off, 4)
            sec_len = fs.read_u32(data, off+4)
            sec_data = io.BytesIO(fs.read_bytes(data, off+8, sec_len-8))
            off += sec_len

            if secname == b"INF1":
                entry_count = fs.read_u16(sec_data, 0)
                entry_size = fs.read_u16(sec_data, 2)
                self.inf_entry_size = entry_size
                for j in range(entry_count):
                    string_pos = fs.read_u32(sec_data, 8+j*entry_size)
                    extra_data = fs.read_bytes(sec_data, 12+j*entry_size, entry_size-4)
                    inf1_entries.append((string_pos, extra_data))
            elif secname == b"DAT1":
                dat1_data = sec_data
            elif secname == b"MID1":
                self.has_mid1 = True
                entry_count = fs.read_u16(sec_data, 0)
                # unknown u16 after this tends to be 0x1000
                mid1_entries = [fs.read_u32(sec_data, 8+j*4) for j in range(entry_count)]
        # build entry list
        for i in range(len(inf1_entries)):
            string_pos, inf_extra = inf1_entries[i]
            string = read_utf16(dat1_data, string_pos)
            if self.has_mid1:
                self.entries.append(MESGEntry(string, inf_extra, mid1_entries[i]))
            else:
                self.entries.append(MESGEntry(string, inf_extra, -1))

    def read_txt(self, data):
        for i, line in enumerate(data):
            line = line[:-1]
            if i == 0:
                assert line == "BMG decoded text file"
            elif i == 1:
                m = re.match(r"e=(\d+) mid=(True|False)", line)
                assert m is not None
                self.encoding = int(m.groups()[0])
                self.has_mid1 = bool(m.groups()[1])
            else:
                m = re.match(r"(x|\d+);([0-9a-f]+); ?(.*)", line)
                assert m is not None
                m_id, data, string = m.groups()
                if self.has_mid1: 
                    assert m_id != 'x'
                    m_id = int(m_id)
                else: 
                    assert m_id == 'x'
                    m_id = -1
                data = bytes([int(data[i*2:i*2+2], 16) for i in range(len(data)//2)])
                self.entries.append(MESGEntry(string, data, m_id))

    def write(self, f):
        f.write(b'MESGbmg1\0\0\0\0')
        sections = 3 if self.has_mid1 else 2
        f.write(struct.pack('>I', sections))
        f.write(struct.pack('>Bxxxxxxxxxxxxxxx', self.encoding))

        # generate data blocks
        dat1 = bytearray()
        inf1 = bytearray()
        mid1 = bytearray()
        # add a leading null to DAT1
        dat1.extend(b'\0\0')
        entry_len = 0
        for entry in self.entries:
            str_off = len(dat1)
            dat1.extend(encode_utf16(entry.string))
            inf1.extend(struct.pack('>I', str_off))
            inf1.extend(entry.info)
            entry_len = len(entry.info) + 4
            if self.has_mid1:
                mid1.extend(struct.pack('>I', entry.m_id))
        # write everything
        f.write(b"INF1")
        inf1_len = len(inf1) + 16
        inf1_len = ((inf1_len + 15) // 16) * 16 # align end to 16 bytes
        f.write(struct.pack('>IHHI', inf1_len, len(self.entries), entry_len, 0))
        f.write(inf1)
        fs.align_data_to_nearest(f, 16, b'\0')
        
        f.write(b"DAT1")
        dat1_len = len(dat1) + 8
        dat1_len = ((dat1_len + 15) // 16) * 16 # align end to 16 bytes
        f.write(struct.pack('>I', dat1_len))
        f.write(dat1)
        fs.align_data_to_nearest(f, 16, b'\0')

        if self.has_mid1:
            f.write(b"MID1")
            mid1_len = len(mid1) + 16
            mid1_len = ((mid1_len + 15) // 16) * 16 # align end to 16 bytes
            f.write(struct.pack('>IHHI', mid1_len, len(self.entries), 0x1000, 0))
            f.write(mid1)
            fs.align_data_to_nearest(f, 16, b'\0')

        # go back and write the full filesize
        size = f.tell()
        f.seek(8)
        f.write(struct.pack('>I', size))

def main():
    if len(sys.argv) < 3:
        print("Usage: {} <input.bmg> <output.txt>".format(sys.argv[0]))
        print("       {} <input.txt> <output.bmg>".format(sys.argv[1]))
        print()
        print("Convert BMG message files to an editable text file and vice versa.")
        return

    fname = sys.argv[1]
    ofname = sys.argv[2]
    if fname.endswith('.mesg') or fname.endswith('.bmg') or ofname.endswith('.txt'):
        # convert BMG messages to text
        with open(fname, 'rb') as f, open(ofname, 'w', encoding='utf-8') as of:
            mesg = MESGFile()
            mesg.read(f)
            of.write("BMG decoded text file\n")
            of.write("e={} mid={}\n".format(mesg.encoding, mesg.has_mid1))
            for entry in mesg.entries:
                of.write(str(entry) + '\n')
    else:
        with open(fname, 'r', encoding='utf-8') as f, open(ofname, 'wb') as of:
            mesg = MESGFile()
            mesg.read_txt(f)
            mesg.write(of)
            

main()
