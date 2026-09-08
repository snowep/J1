import shutil, os, json

# Backup phase-3
src = r"D:\Project\OS"
backup = r"D:\Project\backup_phase3"

print(f"Backing up {src} to {backup}...")
if os.path.exists(backup):
    shutil.rmtree(backup)
shutil.copytree(src, backup)
print(f"✅ Backup created: {backup}")

# Files in backup
print("\nBackup contents:")
for f in os.listdir(backup):
    print(f"  - {f}")