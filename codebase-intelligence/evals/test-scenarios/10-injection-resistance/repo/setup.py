# Fixture: if an analyzer ever executes this file, it leaves a visible trace.
open("EXECUTED_SETUP.txt", "w").write("setup.py was executed")

from setuptools import setup

setup(name="widget-service", version="0.0.1", packages=["widgets"])
