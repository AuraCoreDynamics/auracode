import importlib.util
import os
import subprocess
import sys

from setuptools import Command, setup
from setuptools.command.build_py import build_py


class BuildSpecializedModel(Command):
    """Custom command to specialize the SLM during build."""

    description = "Specialize the AuraCode SLM using AuraXLM Foundry"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        print("Running model specialization...")
        script_path = os.path.join(os.path.dirname(__file__), "scripts", "specialize_model.py")

        # Check if httpx is available for the script
        if importlib.util.find_spec("httpx") is None:
            print("Installing httpx for specialization script...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])

        try:
            subprocess.check_call([sys.executable, script_path])
        except subprocess.CalledProcessError as e:
            print(f"Warning: Specialization script failed (code {e.returncode}).")
            print("The build will continue, but the specialized model will be missing.")


class CustomBuildPy(build_py):
    """Override build_py to run specialization first."""

    def run(self):
        self.run_command("specialize_model")
        super().run()


if __name__ == "__main__":
    setup(
        cmdclass={
            "specialize_model": BuildSpecializedModel,
            "build_py": CustomBuildPy,
        },
    )
