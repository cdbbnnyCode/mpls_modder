This is a small set of tools for editing the text in the Wii Motion Plus Instructional Video that is present
in most (if not all) Wii games that support Wii Motion Plus.

This program currently works with Skyward Sword, but it should also work with other games as long as the 
`player.dol` has the following MD5 hash:

```
274e4795445b367edebf27834283f1c0
```

There are a few different versions of the application in different games; the patching script is currently
incompatible with these other versions.

### Setup

This project requires Python 3.8 or higher.

1. Clone/download this repository
2. Install [gclib](https://github.com/LagoLunatic/gclib):
   ```
   pip install gclib @ git+https://github.com/LagoLunatic/gclib.git
   ```

### Usage

1. Extract the game files and locate the `player.dol` file (typically in `sys/mpls_movie`).
2. Dump the BMG files from `player.dol`:
   ```
   python mpls_modder.py <path to player.dol> --dump
   ```
3. Convert the desired BMG file to text:
   ```
   python bmgtool.py us_en.bmg us_en.txt
   ```
4. Edit the text file
5. Convert the text file back to BMG format:
   ```
   python bmgtool.py us_en.txt us_en_mod.bmg
   ```
6. Patch the modified BMG file into the `player.dol`:
   ```
   python mpls_modder.py <path to player.dol> --patch us_en_mod.bmg
   ```

### Text file formatting

The text file includes a lot of extra formatting that encodes various metadata needed to reconstruct the BMG file.
Each line consists of:

```
message ID;INF1 metadata; text
```

The message ID and metadata should be left alone; the metadata is stored as raw hex data since its meaning is
implementation-dependent.

Additionally, there are markers in the text that denote various formatting flags. These look like `{xx:yyyy:zzzz...}`.
For the Motion Plus application, the only known formatting marker sets the text color: `{ff:0000:xx00}`, where `xx` is
the color code. Known colors are:

* `00`: Default
* `01`: Black
* `02`: Green
* `03`: Blue
* `04`: Purple
* `05`: Red
* `06`: Purple
* `07`: Black
* `08`: Purple

Finally, there are a few characters that are escaped with `\`:

* `\n`: newline
* `\{`: a literal `{` character
* `\}`: a literal `}` character
* `\\`: a literal `\` character

### Limitations

The patching script operates by pasting the modified BMG file over the original BMG files in the program.
While this allows the file to expand significantly, file size is still limited to 18176 bytes.

Additionally, the extra space is gained by overwriting the Spanish and French localizations. In the patched
program, all localizations will use the same BMG file.

The font file used for the application is minified, removing some letters (`jqzFHJQUXZ`), all numbers except 3, and
most punctuation/other characters. If more letters are needed, the BRFNT files can be replaced with more complete
ones.
