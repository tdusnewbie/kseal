import subprocess
import os

os.environ['EDITOR'] = 'nvim --server /tmp/test.sock --remote-wait'
import shlex
print(shlex.split(os.environ['EDITOR']))
