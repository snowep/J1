import importlib
mods = ['yaml', 'pytest', 'requests', 'bs4', 'dateutil']
for m in mods:
    try:
        importlib.import_module(m)
        print(f"OK      {m}")
    except Exception as e:
        print(f"MISSING {m}: {e}")