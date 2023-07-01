import os, sys

def path_resolver():
    # determine if application is a script file or frozen exe
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    elif __file__:
        return os.path.dirname(__file__)