import importlib.util
import os
import sys

# 1. Get the directory where main.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Point to the folder where your CODE actually lives (.venv)
# Note: Changing this from .venv to .venv
performer_path = os.path.join(BASE_DIR, ".venv", "perfomer.py")

if not os.path.exists(performer_path):
    print(f"❌ Still can't find it at: {performer_path}")
    # Let's see what is actually inside that .venv folder
    env_folder = os.path.join(BASE_DIR, ".venv")
    if os.path.exists(env_folder):
        print(f"Contents of .venv folder: {os.listdir(env_folder)}")
    sys.exit(1)

# 3. Load the module
spec = importlib.util.spec_from_file_location("performer", performer_path)
oig_mod = importlib.util.module_from_spec(spec)

# Add .venv to path so it can find auth_utils.py, etc.
sys.path.append(os.path.join(BASE_DIR, ".venv"))

spec.loader.exec_module(oig_mod)

if __name__ == "__main__":
    performer = oig_mod.OIGPerformer()
    performer.run()