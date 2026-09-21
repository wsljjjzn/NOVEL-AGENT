"""Hex dump around JSON error position."""
with open("data/samples/analysis_results.json", "rb") as f:
    data = f.read()

# Check exact bytes at the error position
start = 1150
for i in range(start, min(start + 50, len(data))):
    b = data[i]
    if b == 0x22:
        print(f"pos {i}: STRAIGHT QUOTE (0x22) - ASCII double quote!")
    elif b == 0x5c:
        print(f"pos {i}: BACKSLASH (0x5c)")
    elif b < 32:
        print(f"pos {i}: control char 0x{b:02x}")
    else:
        print(f"pos {i}: byte 0x{b:02x} ({chr(b) if 32 <= b < 127 else '?'})")
