from gclib import fs_helpers as fs
from gclib import dol
import io
import os
import argparse
import hashlib
import shutil

def load_dol(fname):
    dolfile = dol.DOL()
    with open(fname, 'rb') as f:
        data_bytes = f.read()
        md5 = hashlib.md5(data_bytes).hexdigest()
        data = io.BytesIO(data_bytes)
        dolfile.read(data)
    return dolfile, md5

def dump_mesg(dolfile, addr, fname):
    off = dolfile.convert_address_to_offset(addr)
    # 0x08: file size in bytes
    mesg_size = fs.read_u32(dolfile.data, off + 8)
    with open(fname, 'wb') as of:
        of.write(fs.read_bytes(dolfile.data, off, mesg_size))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('-d', '--dump', action='store_true', help="Dump the message files from a vanilla player.dol")
    p.add_argument('-p', '--patch', metavar='<message file>', help="Patch a message file into player.dol")
    p.add_argument('file', help="Path to the player.dol")
    
    args = p.parse_args()

    dolfile, md5 = load_dol(args.file)

    orig_md5 = '274e4795445b367edebf27834283f1c0'

    print("Loaded player.dol, md5={}".format(md5))

    # TODO there are different versions of this program, which have the same text files but slightly different
    # code (probably due to some bug fix). It should be possible to identify the locations of these files by
    # scanning for BMG headers and then finding the address references in the assembly.
    modified = md5 != orig_md5
    if modified:
        print("This player.dol appears to be modified")
        print("Currently, the program cannot dump messages from a modified player.dol, but it can "
                + "patch new message files into one.")
        print("If this is an unmodified player.dol, it is currently incompatible with this program.")

    if not args.dump and not args.patch:
        print("Nothing else to do! Please specify --dump or --patch")
        return

    # addresses (in increasing order)
    msg_french_addr = 0x801683c0
    msg_spanish_addr = 0x80169c00
    msg_english_addr = 0x8016b360

    # load instruction addresses (to the lis instruction)
    # there is an addi for the second half 2 instructions later
    msg_en_load = 0x8000c688
    msg_sp_load = 0x8000c6f8
    msg_fr_load = 0x8000c6c0

    if args.dump and not modified:
        print("dumping message files")
        dump_mesg(dolfile, msg_french_addr, "us_fr.bmg")
        dump_mesg(dolfile, msg_spanish_addr, "us_sp.bmg")
        dump_mesg(dolfile, msg_english_addr, "us_en.bmg")

    if args.patch:
        mod_msgfile = args.patch

        if not modified:
            print("Backing up original {} to player.dol.bak".format(args.file))
            shutil.copy2(args.file, "player.dol.bak")

        print("patching player.dol with modded message file {}".format(mod_msgfile))

        dest_addr = msg_french_addr
        with open(mod_msgfile, "rb") as f:
            # write our new message file to the msg_french_addr
            dolfile.write_data(fs.write_bytes, dest_addr, f.read())

        # patch load instructions
        for load_addr in [msg_en_load, msg_sp_load, msg_fr_load]:

            addr_lo = dest_addr & 0xffff
            addr_hi = (dest_addr >> 16) & 0xffff
            if addr_lo & 0x8000:
                # since addi sign-extends, we need to add 1 to addr_hi if addr_lo is 'negative'
                addr_hi += 1
                addr_hi &= 0xffff

            # @ load_addr: lis r4, addr_hi (bits 15:0)
            inst_lis = dolfile.read_data(fs.read_u32, load_addr)
            inst_lis &= 0xffff0000
            inst_lis |= addr_hi
            dolfile.write_data(fs.write_u32, load_addr, inst_lis)

            # @ load_addr+8: addi r4, r4, addr_lo
            inst_addi = dolfile.read_data(fs.read_u32, load_addr+8)
            inst_addi &= 0xffff0000
            inst_addi |= addr_lo
            dolfile.write_data(fs.write_u32, load_addr+8, inst_addi)

        with open(args.file, "wb") as of:
            of.write(dolfile.data.getvalue())

main()
