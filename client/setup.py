# Hazırlayan: MEB Atakan ÜNVER

import subprocess
import sys

print("Installing requirements...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

print("\n✅ Setup complete! Copy the .example config files under config/ to their "
      "real names (see README.md), then run 'python main.py' to start FARABİ.")
