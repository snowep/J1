"""Debug safe_join with sub/../escape.md."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.utils import safe_join, is_within
from core.filesystem import FileSystem

ws = os.path.realpath(os.path.join(os.getcwd(), "workspace"))
print("ws real:", ws)
print("safe_join:", safe_join(ws, "sub/../escape.md"))

# What does abspath give?
joined = os.path.abspath(os.path.join(ws, "sub/../escape.md"))
print("abspath joined:", joined)
print("realpath:", os.path.realpath(joined))
print("commonpath:", os.path.commonpath([ws, os.path.realpath(joined)]))
print("is_within:", is_within(os.path.join(ws, "sub/../escape.md"), ws))

fs = FileSystem("workspace")
r = fs.write("sub/../escape.md", "x")
print("fs.write:", r)