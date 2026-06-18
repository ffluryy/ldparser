Small tool to parse MoTec ld files.

Primarily, this parser was written to parse telemetry information of ld files written by Assetto Corsa Competizione, see also the related project ['acctelemetry'](https://github.com/gotzl/acctelemetry). However, the parser should work with other ld files as well.
It was tested with the sample ld files that come with a MoTec Mi2 Pro installation as well as with files written by ACC.

The decoding of the ld file is solely based on reverse engineering the binary data.
As of now, ldx files are not considered.

## Reverse-engineered writer notes

This fork includes additional writer behavior needed for generated logs to work
with MoTeC i2 math channels and Data Properties lookups:

- The fixed channel metadata header is 124 bytes.
- The channel display unit is the 8-byte text field immediately after the
  32-byte channel name/id field.
- MoTeC i2 uses that 8-byte display-unit field to bind a channel to its global
  Data Properties quantity. For example, `rpm` must be written as
  `72 70 6d 00 00 00 00 00`.
- Unitless channels must write eight null bytes in the display-unit field.
- The following 8-byte and 12-byte unknown fields are not required for unit
  quantity binding; generated channels leave them as their default values unless
  an existing parsed channel already carries values there.
- Generated files are written with an M1/pro-enabled header. The old ADL-style
  header can produce openable logs whose channels appear unitless in i2 even
  when the display-unit bytes are correct.

The display-unit lookup table in `ldChan` was derived from a known-good M1 log
and is intentionally limited to the 8-byte display-unit field. It is not a full
definition of MoTeC's Data Properties table.

## Usage
See the __main__ function on how to use the tool.

As an example, the __main__ function reads all ld files in a given directory and creates some plots. 
Invoke with

```bash
python ldparser.py /path/to/some/dir
```
